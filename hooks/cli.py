#!/usr/bin/env python3
"""AC Good Boy 命令行。

    cli.py rules                 列出全部规则和当前动作
    cli.py manual                显示用户手册
    cli.py status                显示版本、来源、更新状态
    cli.py update                立即检查更新
    cli.py auto-update           SessionStart 用：到时间才检查，有更新时输出提醒
    cli.py set <编号|high|medium> <block|ask|warn|off>
    cli.py admin [--port N]      在后台启动管理后台，打印地址
    cli.py admin --serve         在前台运行管理后台
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

ADMIN_FILE = os.path.join(lib.HOME, "admin.json")
IDLE_SECONDS = 3600


def cmd_rules(_args):
    config = lib.load_config()
    doc, source = lib.rules_doc()
    print(f"违规清单 v{doc['version']}（{'已自动更新' if source == 'cache' else '内置'}）\n")
    print("| 编号 | 规则 | 为什么 | 动作 |")
    print("| --- | --- | --- | --- |")
    for rule in lib.all_rules(config):
        print(f"| {rule['id']} | {rule['title']} | {rule['why']} | {lib.ACTION_LABELS[rule['action']]} |")
    print("| R00 | 不让 AI 自己关掉守卫 | 修改配置或已安装的清单必须由你本人确认（不可关闭） | ❓ 需确认 |")


def cmd_manual(_args):
    print(lib.manual_text())


def cmd_status(_args):
    doc, source = lib.rules_doc()
    state = lib.load_state()
    config = lib.load_config()
    last = state.get("last_check")
    print(f"违规清单版本：v{doc['version']}（{'已自动更新' if source == 'cache' else '内置'}）")
    print(f"配置目录：{lib.HOME}")
    print(f"自动更新：{'开启' if config['update']['enabled'] else '关闭'}，每 {config['update']['interval_hours']} 小时，来源 {config['update']['base_url']}")
    print(f"上次检查：{time.strftime('%Y-%m-%d %H:%M', time.localtime(last)) if last else '从未'}，{state.get('last_result', '')}")


def cmd_update(_args):
    print(lib.check_update(force=True)[1])


def cmd_auto_update(_args):
    updated, message = lib.check_update()
    if updated:
        json.dump({"systemMessage": f"🐶 AC Good Boy：{message}"}, sys.stdout, ensure_ascii=False)


def cmd_set(args):
    if len(args) != 2 or args[1] not in lib.ACTIONS:
        sys.exit(f"用法：cli.py set <编号|high|medium> <{'|'.join(lib.ACTIONS)}>")
    target, action = args
    config = lib.load_config()
    if target in lib.SEVERITIES:
        config["default_actions"][target] = action
    elif target in {r["id"] for r in lib.all_rules(config)}:
        config["rules"][target] = {"action": action}
    else:
        sys.exit(f"没有这条规则：{target}")
    lib.save_config(config)
    print(f"{target} → {lib.ACTION_LABELS[action]}")


# ---------- 管理后台 ----------

def api_state():
    config = lib.load_config()
    doc, source = lib.rules_doc()
    return {
        "config": config,
        "rules": lib.all_rules(config),
        "rules_version": doc["version"],
        "rules_updated": doc.get("updated", ""),
        "source": source,
        "state": lib.load_state(),
        "manual": lib.manual_text(),
        "home": lib.HOME,
    }


def make_handler(token, page, touch):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, code, body, content_type="application/json; charset=utf-8"):
            data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _allowed(self, query_token=None):
            # 只接受本机地址访问（防 DNS rebinding），且必须带启动时生成的令牌（防其他网页跨站调用）
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost"):
                return False
            given = query_token or self.headers.get("X-AC-Token") or ""
            return secrets.compare_digest(given, token)

        def do_GET(self):
            touch()
            url = urlparse(self.path)
            if url.path == "/":
                if not self._allowed(parse_qs(url.query).get("token", [""])[0]):
                    return self._send(403, "令牌无效，请重新运行 /ac-good-boy:admin 获取地址。", "text/plain; charset=utf-8")
                return self._send(200, page.replace("__TOKEN__", token), "text/html; charset=utf-8")
            if not self._allowed():
                return self._send(403, {"error": "forbidden"})
            if url.path == "/api/state":
                return self._send(200, api_state())
            self._send(404, {"error": "not found"})

        def do_POST(self):
            touch()
            if not self._allowed():
                return self._send(403, {"error": "forbidden"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(min(length, lib.MAX_DOWNLOAD)) or b"{}")
            except ValueError:
                return self._send(400, {"error": "请求不是合法 JSON"})
            path = urlparse(self.path).path
            try:
                if path == "/api/config":
                    config = lib.load_config()
                    for key in lib.DEFAULT_CONFIG:
                        if key in body:
                            config[key] = body[key]
                    lib.save_config(config)
                    return self._send(200, api_state())
                if path == "/api/update":
                    updated, message = lib.check_update(force=True)
                    return self._send(200, dict(api_state(), message=message))
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            self._send(404, {"error": "not found"})

    return Handler


def serve(port):
    token = secrets.token_urlsafe(24)
    with open(os.path.join(lib.HERE, "admin.html"), encoding="utf-8") as f:
        page = f.read()
    last = [time.time()]

    def touch():
        last[0] = time.time()

    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, page, touch))
    port = server.server_address[1]
    info = {"pid": os.getpid(), "port": port, "url": f"http://127.0.0.1:{port}/?token={token}"}
    os.makedirs(lib.HOME, exist_ok=True)
    fd = os.open(ADMIN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(info, f)

    def watchdog():  # 闲置 1 小时自动退出
        while time.time() - last[0] < IDLE_SECONDS:
            time.sleep(30)
        server.shutdown()

    threading.Thread(target=watchdog, daemon=True).start()
    print(info["url"], flush=True)
    try:
        server.serve_forever()
    finally:
        try:
            os.remove(ADMIN_FILE)
        except OSError:
            pass


def running_admin():
    try:
        with open(ADMIN_FILE) as f:
            info = json.load(f)
        with socket.create_connection(("127.0.0.1", info["port"]), timeout=1):
            return info
    except (OSError, ValueError, KeyError):
        return None


def cmd_admin(args):
    port = int(args[args.index("--port") + 1]) if "--port" in args else 8765
    if "--serve" in args:
        return serve(port)
    info = running_admin()
    if not info:
        try:
            with socket.create_server(("127.0.0.1", port)):
                pass
        except OSError:
            port = 0  # 端口被占用就随机挑一个
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "admin", "--serve", "--port", str(port)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        for _ in range(50):
            time.sleep(0.1)
            info = running_admin()
            if info:
                break
    if not info:
        sys.exit("管理后台启动失败")
    print(f"AC Good Boy 管理后台：{info['url']}")
    print("（只能在本机打开；闲置 1 小时自动关闭）")


COMMANDS = {
    "rules": cmd_rules, "manual": cmd_manual, "status": cmd_status, "update": cmd_update,
    "auto-update": cmd_auto_update, "set": cmd_set, "admin": cmd_admin,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]](sys.argv[2:])
