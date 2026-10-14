#!/usr/bin/env python3
"""AC Good Boy 守卫脚本：检查提示词 / 工具调用是否触碰 Claude 使用条款红线。

用法（由 Claude Code hooks 调用，从 stdin 读取 hook 输入 JSON）：
    guard.py prompt   # UserPromptSubmit
    guard.py tool     # PreToolUse

每条规则的动作（block 禁止 / ask 需确认 / warn 提醒 / off 关闭）在后台设置，
见 `cli.py admin`。
"""
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

ALLOW_MARKER = "ac-good-boy:allow"
MAX_SCAN = 200_000
ACTION_RANK = {"warn": 0, "ask": 1, "block": 2}

# 防篡改：Claude 自己改配置、改已安装的清单或用命令关规则时，一律需要你确认。
# 这条写死在代码里，后台和自动更新都不能关掉它。
TAMPER_RULE = {
    "id": "R00",
    "title": "不让 AI 自己关掉守卫",
    "why": "修改 AC Good Boy 的配置或已安装的违规清单，必须由你本人确认。",
    "action": "ask",
}
TAMPER_PATHS = [
    re.compile(re.escape(lib.HOME), re.IGNORECASE),
    re.compile(r"\.ac-good-boy[/\\]", re.IGNORECASE),
    re.compile(r"\.claude[/\\]plugins[/\\].*ac-good-boy", re.IGNORECASE),
]
TAMPER_COMMANDS = [
    re.compile(re.escape(lib.HOME), re.IGNORECASE),
    re.compile(r"\.ac-good-boy[/\\]", re.IGNORECASE),
    re.compile(r"AC_GOOD_BOY_HOME"),
    re.compile(r"cli\.py\"?\s+(set|import)\b"),
    re.compile(r"(sed\s+-i|>|\brm\b|\bmv\b|\bcp\b|\btee\b|\bchmod\b).*\.claude[/\\]plugins[/\\]\S*ac-good-boy", re.IGNORECASE),
]


def find_violations(text, rules, source):
    hits = []
    for rule in rules:
        if rule.get("tools_only") and source != "tool":
            continue
        if any(all(p.search(text) for p in group) for group in rule["_groups"]):
            hits.append(rule)
    return hits


def ignored_patterns(cwd, config):
    patterns = list(config["ignore_paths"])
    try:
        with open(os.path.join(cwd or ".", ".ac-good-boy-ignore"), encoding="utf-8") as f:
            patterns += [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except OSError:
        pass
    return patterns


def is_ignored(file_path, cwd, config):
    if not file_path:
        return False
    absolute = os.path.abspath(os.path.join(cwd or ".", file_path))
    if absolute.startswith(lib.PLUGIN_ROOT + os.sep):
        return True
    relative = os.path.relpath(absolute, os.path.abspath(cwd or "."))
    return any(fnmatch.fnmatch(relative, p) or fnmatch.fnmatch(absolute, p) for p in ignored_patterns(cwd, config))


def tool_parts(data):
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    parts = []
    for key in ("command", "content", "new_string", "new_source", "url", "query", "prompt"):
        value = tool_input.get(key)
        if isinstance(value, str):
            parts.append(value)
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            parts.append(edit["new_string"])
    return file_path, "\n".join(parts)


def is_tampering(file_path, command):
    return any(p.search(file_path) for p in TAMPER_PATHS) or any(p.search(command) for p in TAMPER_COMMANDS)


def strongest(hits):
    return max((h["action"] for h in hits), key=lambda a: ACTION_RANK[a])


def describe(hits, action):
    head = {"block": "⛔ 已禁止", "ask": "❓ 需要你确认", "warn": "⚠️ 提醒"}[action]
    lines = [f"🐶 AC Good Boy {head}：检测到可能违反 Claude 使用条款的操作"]
    for rule in hits:
        lines.append(f"  [{rule['id']}] {rule['title']} —— {rule['why']}")
    lines.append("误报？可在内容里加 ac-good-boy:allow，或在后台（/ac-good-boy:admin）调整规则。")
    return "\n".join(lines)


def claude_note(hits):
    ids = "、".join(f"{r['id']} {r['title']}" for r in hits)
    return (
        f"AC Good Boy 合规提醒：本次内容可能触碰以下规则：{ids}。"
        "请先向用户明确指出风险，不要协助任何违反 Anthropic 使用条款或使用政策的部分，"
        "也不要尝试绕过或关闭 AC Good Boy；如有合规的替代做法（例如使用官方 API Key、"
        "遵守限额、不使用输出训练竞品模型），请给出建议。"
    )


def handle_prompt(data, rules):
    text = data.get("prompt") or ""
    if ALLOW_MARKER in text:
        return None
    hits = find_violations(text[:MAX_SCAN], rules, "prompt")
    if not hits:
        return None
    action = strongest(hits)
    if action == "block":
        return {"decision": "block", "reason": describe(hits, action)}
    return {
        "systemMessage": describe(hits, "warn"),
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": claude_note(hits)},
    }


def handle_tool(data, rules, config):
    file_path, body = tool_parts(data)
    command = (data.get("tool_input") or {}).get("command") or ""
    hits = []
    if is_tampering(file_path, command):
        hits.append(TAMPER_RULE)
    if not is_ignored(file_path, data.get("cwd"), config) and ALLOW_MARKER not in body:
        hits += find_violations((file_path + "\n" + body)[:MAX_SCAN], rules, "tool")
    if not hits:
        return None
    action = strongest(hits)
    message = describe(hits, action)
    specific = {"hookEventName": "PreToolUse", "additionalContext": claude_note(hits)}
    if action in ("block", "ask"):
        specific["permissionDecision"] = "deny" if action == "block" else "ask"
        specific["permissionDecisionReason"] = message
    return {"systemMessage": message, "hookSpecificOutput": specific}


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "tool"
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    config = lib.load_config()
    rules = lib.active_rules(config)
    result = handle_prompt(data, rules) if source == "prompt" else handle_tool(data, rules, config)
    if result:
        json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
