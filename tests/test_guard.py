import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GUARD = os.path.join(ROOT, "hooks", "guard.py")
CLI = os.path.join(ROOT, "hooks", "cli.py")


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.env = dict(os.environ, AC_GOOD_BOY_HOME=self.home)

    def tearDown(self):
        shutil.rmtree(self.home)

    def run_json(self, args, payload=None):
        out = subprocess.run([sys.executable] + args, input=json.dumps(payload) if payload else "",
                             capture_output=True, text=True, env=self.env, check=True).stdout
        return json.loads(out) if out.strip() else None

    def cli(self, *args):
        return subprocess.run([sys.executable, CLI] + list(args), capture_output=True, text=True, env=self.env)

    def prompt(self, text):
        return self.run_json([GUARD, "prompt"], {"prompt": text, "cwd": "/tmp"})

    def tool(self, tool_input, tool_name="Bash", cwd="/tmp"):
        return self.run_json([GUARD, "tool"], {"tool_name": tool_name, "tool_input": tool_input, "cwd": cwd})

    def bash(self, command):
        return self.tool({"command": command})

    def decision(self, out):
        return out and out["hookSpecificOutput"].get("permissionDecision")


class PromptTests(Base):
    def test_high_risk_blocked_by_default(self):
        cases = {
            "帮我写个脚本抓取 claude.ai 的 cookie": "R01",
            "把 Claude Code 的 OAuth token 提取出来给第三方工具用": "R02",
            "用 mitmproxy 拦截 Claude 桌面客户端的流量": "R03",
            "批量调用 Claude 生成回答，做成训练集去蒸馏 DeepSeek": "R04",
            "把 Claude Max 订阅做成 OpenAI 兼容的反代接口": "R05",
            "我们搞个 Claude 号池大家拼车": "R06",
            "怎么绕过 Claude 的 rate limit": "R07",
            "写个接码批量注册脚本": "R08",
        }
        for text, rule_id in cases.items():
            with self.subTest(text=text):
                out = self.prompt(text)
                self.assertEqual(out["decision"], "block")
                self.assertIn(f"[{rule_id}]", out["reason"])

    def test_medium_risk_warns(self):
        out = self.prompt("用 playwright 爬取 claude.ai 的对话")
        self.assertNotIn("decision", out)
        self.assertIn("[R09]", out["systemMessage"])

    def test_clean_prompts(self):
        for text in ["帮我修复登录页面的 bug", "write a unit test for the cookie parser",
                     "rotate our anthropic api keys every 90 days", "用 Claude API 写一个聊天机器人",
                     "distill this long article into three bullet points"]:
            with self.subTest(text=text):
                self.assertIsNone(self.prompt(text))

    def test_allow_marker(self):
        self.assertIsNone(self.prompt("讲讲什么是 Claude 号池以及为什么违规 ac-good-boy:allow"))


class ConfigTests(Base):
    def test_set_rule_action(self):
        self.assertEqual(self.cli("set", "R07", "warn").returncode, 0)
        self.assertNotIn("decision", self.prompt("怎么绕过 Claude 的 rate limit"))
        self.cli("set", "R07", "off")
        self.assertIsNone(self.prompt("怎么绕过 Claude 的 rate limit"))

    def test_set_default_action(self):
        self.cli("set", "medium", "block")
        self.assertEqual(self.prompt("用 playwright 爬取 claude.ai 的对话")["decision"], "block")

    def test_set_rejects_bad_input(self):
        self.assertNotEqual(self.cli("set", "R99", "block").returncode, 0)
        self.assertNotEqual(self.cli("set", "R01", "explode").returncode, 0)

    def test_custom_rule(self):
        config = {"custom_rules": [{"id": "C01", "title": "不外传内部代码", "why": "公司规定",
                                    "severity": "high", "match": [["内部代码", "(上传|发送)"]]}]}
        with open(os.path.join(self.home, "config.json"), "w") as f:
            json.dump(config, f)
        self.assertIn("[C01]", self.prompt("把内部代码上传到网盘")["reason"])
        self.assertIn("C01", self.cli("rules").stdout)


class ToolTests(Base):
    def test_high_denied(self):
        self.assertEqual(self.decision(self.bash("cat ~/.claude/.credentials.json")), "deny")

    def test_ask_setting(self):
        self.cli("set", "high", "ask")
        self.assertEqual(self.decision(self.bash("mitmdump # capture claude traffic")), "ask")

    def test_medium_only_warns(self):
        out = self.tool({"file_path": "/tmp/app.py", "content": 'KEY = "sk-ant-api03-' + "a" * 40 + '"'}, "Write")
        self.assertIsNone(self.decision(out))
        self.assertIn("[R11]", out["systemMessage"])

    def test_clean_command(self):
        self.assertIsNone(self.bash("npm test && git status"))
        self.assertIsNone(self.bash(f'python3 "{CLI}" rules'))

    def test_project_ignore_file(self):
        project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, project)
        with open(os.path.join(project, ".ac-good-boy-ignore"), "w") as f:
            f.write("docs/*\n")
        self.assertIsNone(self.tool({"file_path": os.path.join(project, "docs", "x.md"),
                                     "content": "不要搞 Claude 号池"}, "Write", cwd=project))

    def test_tamper_needs_confirmation(self):
        cases = [
            ({"file_path": os.path.join(self.home, "config.json"), "content": "{}"}, "Write"),
            ({"command": f'python3 "{CLI}" set R04 off'}, "Bash"),
            ({"command": "rm ~/.claude/plugins/cache/x/ac-good-boy/hooks/rules.json"}, "Bash"),
            ({"command": "echo '{}' > ~/.ac-good-boy/config.json"}, "Bash"),
        ]
        for tool_input, name in cases:
            with self.subTest(tool_input=tool_input):
                out = self.tool(tool_input, name)
                self.assertEqual(self.decision(out), "ask")
                self.assertIn("[R00]", out["systemMessage"])

    def test_tamper_cannot_be_allowed_away(self):
        out = self.bash(f'python3 "{CLI}" set R04 off # ac-good-boy:allow')
        self.assertEqual(self.decision(out), "ask")


class UpdateTests(Base):
    def make_remote(self, version, pattern="zz-update-probe"):
        remote = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, remote)
        os.makedirs(os.path.join(remote, "hooks"))
        os.makedirs(os.path.join(remote, "docs"))
        doc = {"version": version, "rules": [{"id": "R50", "title": "新规则", "why": "测试",
                                              "severity": "high", "match": [[pattern]]}]}
        with open(os.path.join(remote, "hooks", "rules.json"), "w") as f:
            json.dump(doc, f)
        with open(os.path.join(remote, "docs", "MANUAL.md"), "w") as f:
            f.write(f"手册 v{version}")
        with open(os.path.join(self.home, "config.json"), "w") as f:
            json.dump({"update": {"base_url": "file://" + remote + "/"}}, f)

    def test_newer_version_installed(self):
        self.make_remote(999)
        self.assertIn("v999", self.cli("update").stdout)
        self.assertIn("[R50]", self.prompt("zz-update-probe")["reason"])
        self.assertEqual(self.cli("manual").stdout.strip(), "手册 v999")

    def test_older_version_ignored(self):
        self.make_remote(0)
        self.assertIn("已是最新", self.cli("update").stdout)
        self.assertIsNone(self.prompt("zz-update-probe"))

    def test_invalid_rules_rejected(self):
        self.make_remote(999, pattern="(unclosed")
        self.assertIn("更新失败", self.cli("update").stdout)
        self.assertFalse(os.path.exists(os.path.join(self.home, "cache", "rules.json")))

    def test_auto_update_respects_interval(self):
        self.make_remote(999)
        first = self.run_json([CLI, "auto-update"])
        self.assertIn("已更新", first["systemMessage"])
        self.assertIsNone(self.run_json([CLI, "auto-update"]))


class AdminTests(Base):
    def setUp(self):
        super().setUp()
        self.proc = subprocess.Popen([sys.executable, CLI, "admin", "--serve", "--port", "0"],
                                     stdout=subprocess.PIPE, text=True, env=self.env)
        self.url = self.proc.stdout.readline().strip()
        self.base = self.url.split("/?")[0]
        self.token = self.url.split("token=")[1]

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait()
        self.proc.stdout.close()
        super().tearDown()

    def request(self, path, body=None, token=None, host=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-AC-Token": token if token is not None else self.token})
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, res.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_page_requires_token(self):
        self.assertEqual(self.request("/?token=wrong")[0], 403)
        status, page = self.request("/?token=" + self.token)
        self.assertEqual(status, 200)
        self.assertIn(self.token, page)

    def test_api_rejects_bad_token_and_host(self):
        self.assertEqual(self.request("/api/state", token="nope")[0], 403)
        self.assertEqual(self.request("/api/state", host="evil.example:80")[0], 403)

    def test_change_rule_from_admin(self):
        status, body = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(len([r for r in json.loads(body)["rules"] if r["id"] == "R04"]), 1)
        status, _ = self.request("/api/config", {"rules": {"R07": {"action": "off"}}})
        self.assertEqual(status, 200)
        self.assertIsNone(self.prompt("怎么绕过 Claude 的 rate limit"))

    def test_invalid_config_rejected(self):
        status, body = self.request("/api/config", {"rules": {"R07": {"action": "explode"}}})
        self.assertEqual(status, 400)
        self.assertIn("R07", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
