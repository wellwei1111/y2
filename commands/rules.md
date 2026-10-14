---
description: 列出 AC Good Boy 的全部合规规则
allowed-tools: Read
---

读取 `${CLAUDE_PLUGIN_ROOT}/RULES.md`，把规则表原样展示给用户，然后用一句话说明当前模式：
环境变量 `AC_GOOD_BOY_MODE` 为 `warn`（只提醒）、`ask`（默认，高风险工具调用需确认）或 `strict`（高风险直接拦截）。
