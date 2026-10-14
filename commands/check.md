---
description: 用 AC Good Boy 的规则自查一段需求或方案是否合规
argument-hint: <要检查的需求或方案>
allowed-tools: Bash(python3:*)
---

运行 `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/cli.py" rules` 取得当前规则，逐条对照下面的需求或方案，判断是否可能违反其中任何一条。
对每条可能触碰的规则给出编号、原因和合规的替代做法；全部合规就明确说"合规 ✅"。

需求或方案：

$ARGUMENTS
