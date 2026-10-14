#!/usr/bin/env python3
"""AC Good Boy 守卫脚本：检查提示词 / 工具调用是否触碰 Claude 使用条款红线。

用法（由 Claude Code hooks 调用，从 stdin 读取 hook 输入 JSON）：
    guard.py prompt   # UserPromptSubmit
    guard.py tool     # PreToolUse

环境变量 AC_GOOD_BOY_MODE：
    warn   只提醒，从不拦截
    ask    （默认）提醒；高风险工具调用需要你手动确认
    strict 高风险提示词直接拦截，高风险工具调用直接拒绝
"""
import fnmatch
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
ALLOW_MARKER = "ac-good-boy:allow"
MAX_SCAN = 200_000


def load_rules():
    with open(os.path.join(HERE, "rules.json"), encoding="utf-8") as f:
        rules = json.load(f)["rules"]
    for rule in rules:
        rule["_groups"] = [[re.compile(p, re.IGNORECASE) for p in group] for group in rule["match"]]
    return rules


def find_violations(text, rules, source):
    hits = []
    for rule in rules:
        if rule.get("tools_only") and source != "tool":
            continue
        if any(all(p.search(text) for p in group) for group in rule["_groups"]):
            hits.append(rule)
    return hits


def ignored_paths(cwd):
    path = os.path.join(cwd or ".", ".ac-good-boy-ignore")
    try:
        with open(path, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except OSError:
        return []


def is_ignored(file_path, cwd):
    if not file_path:
        return False
    absolute = os.path.abspath(os.path.join(cwd or ".", file_path))
    if absolute.startswith(PLUGIN_ROOT + os.sep):
        return True
    relative = os.path.relpath(absolute, os.path.abspath(cwd or "."))
    return any(fnmatch.fnmatch(relative, pattern) for pattern in ignored_paths(cwd))


def tool_text(data):
    """拼出需要检查的工具调用文本；返回 None 表示跳过检查。"""
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if is_ignored(file_path, data.get("cwd")):
        return None
    parts = [file_path or ""]
    for key in ("command", "content", "new_string", "new_source", "url", "query", "prompt"):
        value = tool_input.get(key)
        if isinstance(value, str):
            parts.append(value)
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            parts.append(edit["new_string"])
    return "\n".join(parts)


def describe(hits):
    lines = ["🐶 AC Good Boy：检测到可能违反 Claude 使用条款的操作"]
    for rule in hits:
        lines.append(f"  [{rule['id']}] {rule['title']} —— {rule['why']}")
    lines.append("如果是误报，可在内容里加上 ac-good-boy:allow 标记，或把文件路径写进 .ac-good-boy-ignore。")
    return "\n".join(lines)


def claude_note(hits):
    ids = "、".join(f"{r['id']} {r['title']}" for r in hits)
    return (
        f"AC Good Boy 合规提醒：本次内容可能触碰以下规则：{ids}。"
        "请先向用户明确指出风险，不要协助任何违反 Anthropic 使用条款或使用政策的部分；"
        "如有合规的替代做法（例如使用官方 API Key、遵守限额、不使用输出训练竞品模型），请给出建议。"
    )


def handle_prompt(data, rules, mode):
    text = data.get("prompt") or ""
    if ALLOW_MARKER in text:
        return None
    hits = find_violations(text[:MAX_SCAN], rules, "prompt")
    if not hits:
        return None
    message = describe(hits)
    if mode == "strict" and any(r["severity"] == "high" for r in hits):
        return {"decision": "block", "reason": message}
    return {
        "systemMessage": message,
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": claude_note(hits)},
    }


def handle_tool(data, rules, mode):
    text = tool_text(data)
    if text is None or ALLOW_MARKER in text:
        return None
    hits = find_violations(text[:MAX_SCAN], rules, "tool")
    if not hits:
        return None
    message = describe(hits)
    specific = {"hookEventName": "PreToolUse", "additionalContext": claude_note(hits)}
    if any(r["severity"] == "high" for r in hits) and mode in ("ask", "strict"):
        specific["permissionDecision"] = "deny" if mode == "strict" else "ask"
        specific["permissionDecisionReason"] = message
    return {"systemMessage": message, "hookSpecificOutput": specific}


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "tool"
    mode = os.environ.get("AC_GOOD_BOY_MODE", "ask").strip().lower()
    if mode not in ("warn", "ask", "strict"):
        mode = "ask"
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    rules = load_rules()
    result = handle_prompt(data, rules, mode) if source == "prompt" else handle_tool(data, rules, mode)
    if result:
        json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
