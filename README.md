# 🐶 AC Good Boy

**坚决不违规。** 一个开源的 Claude Code 插件：在你提交提示词、以及 Claude 执行命令 / 写文件 / 访问网页之前，检查是否触碰 Anthropic / Claude 使用条款的红线，一旦疑似违规就立即提醒。

完整规则见 [RULES.md](RULES.md)，概览：

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

## 安装

```
/plugin marketplace add wellwei1111/y2
/plugin install ac-good-boy@ac-good-boy
```

依赖：`python3`（只用标准库）。

## 工作方式

| 时机 | 发生什么 |
| --- | --- |
| 你提交提示词（UserPromptSubmit） | 命中规则 → 终端显示提醒，同时告诉 Claude 先指出风险、不协助违规部分 |
| Claude 调用 Bash / Write / Edit / WebFetch 等（PreToolUse） | 命中高风险规则 → 弹出确认，由你决定是否继续；命中提醒级规则 → 只显示提醒 |

命令：

- `/ac-good-boy:rules` — 列出全部规则
- `/ac-good-boy:check <需求或方案>` — 让 Claude 对照规则自查

## 模式

设置环境变量 `AC_GOOD_BOY_MODE`：

| 值 | 行为 |
| --- | --- |
| `warn` | 只提醒，从不拦截 |
| `ask`（默认） | 提醒；高风险工具调用需你手动确认 |
| `strict` | 高风险提示词直接拦截，高风险工具调用直接拒绝 |

## 误报怎么办

- 在提示词或内容里加上 `ac-good-boy:allow`，本次跳过检查。
- 在项目根目录的 `.ac-good-boy-ignore` 里按行写文件路径通配符（如 `docs/*.md`），写入这些文件时不检查。

## 自定义规则

规则都在 [`hooks/rules.json`](hooks/rules.json)：每条规则的 `match` 是若干组正则，任意一组里的正则全部命中即触发。欢迎提 PR 补充规则或修正误报。

运行测试：

```
python3 -m unittest discover -s tests -v
```

## 声明

本插件基于关键词 / 正则做自查提醒，既不能保证发现所有违规，也可能误报；它不构成法律意见。一切以 Anthropic 官方最新的[使用政策](https://www.anthropic.com/legal/aup)和[服务条款](https://www.anthropic.com/legal/consumer-terms)为准。

## License

MIT
