---
description: 打开 AC Good Boy 管理后台，设置哪些动作被禁止
allowed-tools: Bash(python3:*)
---

运行 `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/cli.py" admin`，把输出的后台地址原样告诉用户，并提醒：地址只能在本机浏览器打开，闲置 1 小时自动关闭。
如果用户在云端或远程环境、本机打不开，告诉他们也可以用命令设置：
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/cli.py" set <规则编号|high|medium> <block|ask|warn|off>`（修改设置需要用户本人确认）。
