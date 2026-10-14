# 🐶 AC Good Boy

**坚决不违规。** 一个开源的 Claude Code 插件：在你提交提示词、以及 Claude 执行命令 / 写文件 / 访问网页之前，检查是否触碰 Anthropic / Claude 使用条款的红线，一旦疑似违规就立即提醒。

装上就生效：高风险动作默认**直接禁止**，中风险动作默认提醒。每条规则的动作都能在**管理后台**里改；违规清单和[用户手册](docs/MANUAL.md)会**自动更新**。

| 编号 | 我坚决不…… |
| --- | --- |
| R01 | 抓取 Cookie / 网页会话令牌 |
| R02 | 提取、导出或复用 OAuth / 登录凭证 |
| R03 | 拦截 / 抓包桌面客户端或 Claude Code 的流量 |
| R04 | 批量采集 Claude 输出去训练 / 蒸馏其他模型（如 DeepSeek 等） |
| R05 | 把订阅（Pro / Max）额度包装成 API 或第三方服务 |
| R06 | 共享、出租、转售账号或 API Key，搞号池 |
| R07 | 绕过速率限制或用量上限 |
| R08 | 批量注册账号、绕过地区或身份限制 |
| R09 | 用脚本自动化抓取 claude.ai 网页端 |
| R10 | 逆向、破解或篡改官方客户端 |
| R11 | 硬编码、上传 API Key |
| R12 | 越狱、绕过模型安全机制 |
| R00 | 让 AI 自己关掉守卫（写死在代码里，不可关闭） |

## 安装

```
/plugin marketplace add wellwei1111/y2
/plugin install ac-good-boy@ac-good-boy
```

依赖：`python3`（只用标准库）。

## 工作方式

| 时机 | 发生什么 |
| --- | --- |
| 开始新会话（SessionStart） | 到了检查时间（默认 24 小时）就下载最新违规清单和用户手册 |
| 你提交提示词（UserPromptSubmit） | 命中"禁止"规则 → 提示词被拦下；命中其他规则 → 提醒，并要求 Claude 不协助违规部分 |
| Claude 调用 Bash / Write / Edit / WebFetch 等（PreToolUse） | 按规则动作：⛔ 禁止 / ❓ 需确认 / ⚠️ 提醒 |

## 命令

| 命令 | 作用 |
| --- | --- |
| `/ac-good-boy:admin` | 打开管理后台 |
| `/ac-good-boy:rules` | 列出全部规则和当前动作 |
| `/ac-good-boy:check <方案>` | 对照规则自查一个需求或方案 |
| `/ac-good-boy:update` | 立即更新违规清单和用户手册 |
| `/ac-good-boy:manual` | 查看用户手册 |

## 管理后台

`/ac-good-boy:admin` 会在本机启动一个网页后台（只监听 127.0.0.1，带一次性令牌，闲置 1 小时自动关闭），可以：

- 设置高 / 中风险的默认动作；
- 逐条把规则设为 ⛔ 禁止、❓ 需确认、⚠️ 提醒或关闭；
- 添加自定义禁止项（正则匹配）；
- 设置忽略的文件路径；
- 配置自动更新，或立即检查更新。

没有浏览器的环境可用命令：`python3 hooks/cli.py set <编号|high|medium> <block|ask|warn|off>`。设置保存在 `~/.ac-good-boy/config.json`，插件升级不会覆盖。

## 自动更新

违规清单（`hooks/rules.json`）和用户手册（`docs/MANUAL.md`）从本仓库 `main` 分支自动下载。只采用版本号更高、校验通过的清单；**只下载数据，从不下载或执行代码**。维护者更新清单时，修改 `hooks/rules.json`、把 `version` 加一并合并到 `main`，所有用户会在 24 小时内收到。插件代码本身用 `/plugin` 更新。

## 误报怎么办

- 在提示词或内容里加上 `ac-good-boy:allow`，本次跳过内容检查（防篡改检查不受影响）。
- 在后台或项目根目录的 `.ac-good-boy-ignore` 里加文件路径通配符。
- 在后台把这条规则改成提醒或关闭。

## 自定义规则

规则都在 [`hooks/rules.json`](hooks/rules.json)：每条规则的 `match` 是若干组正则，任意一组里的正则全部命中即触发；`severity` 为 `high` / `medium`。欢迎提 PR 补充规则或修正误报。

运行测试：

```
python3 -m unittest discover -s tests -v
```

## 声明

本插件基于关键词 / 正则做自查提醒，既不能保证发现所有违规，也可能误报；它不构成法律意见。一切以 Anthropic 官方最新的[使用政策](https://www.anthropic.com/legal/aup)和[服务条款](https://www.anthropic.com/legal/consumer-terms)为准。

## License

MIT
