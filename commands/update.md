---
description: 立即检查并更新 AC Good Boy 违规清单和用户手册
allowed-tools: Bash(python3:*)
---

运行 `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/cli.py" update`，再运行 `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/cli.py" status`，把结果告诉用户。
