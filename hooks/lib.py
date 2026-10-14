"""AC Good Boy 共享逻辑：配置、违规清单、自动更新。"""
import json
import os
import re
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
HOME = os.path.expanduser(os.environ.get("AC_GOOD_BOY_HOME") or "~/.ac-good-boy")
CONFIG_PATH = os.path.join(HOME, "config.json")
STATE_PATH = os.path.join(HOME, "state.json")
CACHE_DIR = os.path.join(HOME, "cache")

ACTIONS = ("block", "ask", "warn", "off")
SEVERITIES = ("high", "medium")
ACTION_LABELS = {"block": "⛔ 禁止", "ask": "❓ 需确认", "warn": "⚠️ 提醒", "off": "关闭"}
DEFAULT_UPDATE_URL = "https://raw.githubusercontent.com/wellwei1111/y2/main/"
MAX_DOWNLOAD = 1_000_000

DEFAULT_CONFIG = {
    "default_actions": {"high": "block", "medium": "warn"},
    "rules": {},
    "custom_rules": [],
    "ignore_paths": [],
    "update": {"enabled": True, "base_url": DEFAULT_UPDATE_URL, "interval_hours": 24},
}


# ---------- 读写 ----------

def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _write_json(path, data):
    _write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_config():
    stored = _read_json(CONFIG_PATH, {})
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in stored.items():
        if isinstance(config.get(key), dict) and isinstance(value, dict):
            config[key].update(value)
        elif key in config:
            config[key] = value
    return config


def save_config(config):
    validate_config(config)
    _write_json(CONFIG_PATH, config)


def load_state():
    return _read_json(STATE_PATH, {})


def save_state(state):
    _write_json(STATE_PATH, state)


# ---------- 校验 ----------

def validate_rule(rule, custom=False):
    for key in ("id", "title", "why", "severity", "match"):
        if key not in rule:
            raise ValueError(f"规则缺少字段 {key}")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", str(rule["id"])):
        raise ValueError(f"规则编号不合法：{rule['id']}")
    if custom and not str(rule["id"]).startswith("C"):
        raise ValueError(f"自定义规则编号须以 C 开头：{rule['id']}")
    if rule["severity"] not in SEVERITIES:
        raise ValueError(f"{rule['id']}：severity 只能是 {SEVERITIES}")
    groups = rule["match"]
    if not isinstance(groups, list) or not groups:
        raise ValueError(f"{rule['id']}：match 至少要有一组正则")
    for group in groups:
        if not isinstance(group, list) or not group:
            raise ValueError(f"{rule['id']}：match 的每一组都必须是非空列表")
        for pattern in group:
            try:
                re.compile(pattern)
            except (re.error, TypeError) as e:
                raise ValueError(f"{rule['id']}：正则 {pattern!r} 无效：{e}")


def validate_rules_doc(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("version"), int) or not isinstance(doc.get("rules"), list):
        raise ValueError("违规清单格式不对：需要整数 version 和 rules 列表")
    ids = set()
    for rule in doc["rules"]:
        validate_rule(rule)
        if rule["id"] in ids:
            raise ValueError(f"规则编号重复：{rule['id']}")
        ids.add(rule["id"])


def validate_config(config):
    for severity, action in config["default_actions"].items():
        if severity not in SEVERITIES or action not in ACTIONS:
            raise ValueError(f"默认动作不合法：{severity}={action}")
    for rule_id, override in config["rules"].items():
        if not isinstance(override, dict) or override.get("action") not in ACTIONS:
            raise ValueError(f"{rule_id} 的动作必须是 {ACTIONS}")
    ids = set()
    for rule in config["custom_rules"]:
        validate_rule(rule, custom=True)
        if rule["id"] in ids:
            raise ValueError(f"自定义规则编号重复：{rule['id']}")
        ids.add(rule["id"])
    if not all(isinstance(p, str) for p in config["ignore_paths"]):
        raise ValueError("忽略路径必须是字符串列表")
    update = config["update"]
    if not str(update.get("base_url", "")).startswith(("https://", "file://")):
        raise ValueError("更新地址必须以 https:// 开头")
    if not isinstance(update.get("interval_hours"), (int, float)) or update["interval_hours"] < 1:
        raise ValueError("更新间隔至少 1 小时")


# ---------- 违规清单 ----------

def _bundled_doc():
    return _read_json(os.path.join(HERE, "rules.json"), {"version": 0, "rules": []})


def _cached_doc():
    doc = _read_json(os.path.join(CACHE_DIR, "rules.json"), None)
    try:
        validate_rules_doc(doc)
        return doc
    except ValueError:
        return None


def rules_doc():
    """返回 (清单, 来源)：内置清单和已下载清单里版本更新的那个。"""
    bundled, cached = _bundled_doc(), _cached_doc()
    if cached and cached["version"] > bundled["version"]:
        return cached, "cache"
    return bundled, "bundled"


def manual_text():
    _, source = rules_doc()
    cached = os.path.join(CACHE_DIR, "MANUAL.md")
    path = cached if source == "cache" and os.path.exists(cached) else os.path.join(PLUGIN_ROOT, "docs", "MANUAL.md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "（找不到用户手册）"


def all_rules(config):
    """全部规则（含已关闭），每条附带 action 和 source。"""
    doc, source = rules_doc()
    result = []
    for rule, origin in [(r, source) for r in doc["rules"]] + [(r, "custom") for r in config["custom_rules"]]:
        override = config["rules"].get(rule["id"], {})
        action = override.get("action") or config["default_actions"].get(rule["severity"], "warn")
        result.append(dict(rule, action=action, source=origin))
    return result


def active_rules(config):
    rules = [r for r in all_rules(config) if r["action"] != "off"]
    for rule in rules:
        rule["_groups"] = [[re.compile(p, re.IGNORECASE) for p in group] for group in rule["match"]]
    return rules


# ---------- 自动更新 ----------

def _download(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError(f"{url} 超过 1MB")
    return data.decode("utf-8")


def check_update(config=None, force=False):
    """检查并下载新的违规清单和用户手册。返回 (是否更新, 说明)。

    只下载数据（正则规则和 Markdown 手册），从不下载或执行代码。
    """
    config = config or load_config()
    update = config["update"]
    state = load_state()
    if not force:
        if not update.get("enabled"):
            return False, "自动更新已关闭"
        if time.time() - state.get("last_check", 0) < update["interval_hours"] * 3600:
            return False, "还没到检查时间"
    base = update["base_url"].rstrip("/") + "/"
    state["last_check"] = time.time()
    try:
        doc = json.loads(_download(base + "hooks/rules.json"))
        validate_rules_doc(doc)
        current, _ = rules_doc()
        if doc["version"] <= current["version"]:
            result = (False, f"已是最新（v{current['version']}）")
        else:
            manual = _download(base + "docs/MANUAL.md")
            _write_atomic(os.path.join(CACHE_DIR, "MANUAL.md"), manual)
            _write_json(os.path.join(CACHE_DIR, "rules.json"), doc)
            result = (True, f"违规清单和用户手册已更新：v{current['version']} → v{doc['version']}")
    except Exception as e:  # 网络或格式问题都不能影响正常使用
        result = (False, f"更新失败：{e}")
    state["last_result"] = result[1]
    save_state(state)
    return result
