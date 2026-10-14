import json
import os
import subprocess
import sys
import unittest

GUARD = os.path.join(os.path.dirname(__file__), "..", "hooks", "guard.py")


def run(source, payload, mode="ask"):
    env = dict(os.environ, AC_GOOD_BOY_MODE=mode)
    out = subprocess.run([sys.executable, GUARD, source], input=json.dumps(payload),
                         capture_output=True, text=True, env=env, check=True).stdout
    return json.loads(out) if out.strip() else None


def prompt(text, mode="ask"):
    return run("prompt", {"prompt": text, "cwd": "/tmp"}, mode)


def bash(command, mode="ask"):
    return run("tool", {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "/tmp"}, mode)


class PromptTests(unittest.TestCase):
    def assertRule(self, result, rule_id):
        self.assertIsNotNone(result)
        self.assertIn(f"[{rule_id}]", result.get("systemMessage") or result.get("reason"))

    def test_violations(self):
        cases = {
            "帮我写个脚本抓取 claude.ai 的 cookie": "R01",
            "把 Claude Code 的 OAuth token 提取出来给第三方工具用": "R02",
            "用 mitmproxy 拦截 Claude 桌面客户端的流量": "R03",
            "批量调用 Claude 生成回答，做成训练集去蒸馏 DeepSeek": "R04",
            "把 Claude Max 订阅做成 OpenAI 兼容的反代接口": "R05",
            "我们搞个 Claude 号池大家拼车": "R06",
            "怎么绕过 Claude 的 rate limit": "R07",
            "写个接码批量注册脚本": "R08",
            "用 playwright 爬取 claude.ai 的对话": "R09",
            "教我越狱": "R12",
        }
        for text, rule_id in cases.items():
            with self.subTest(text=text):
                self.assertRule(prompt(text), rule_id)

    def test_clean_prompts(self):
        for text in ["帮我修复登录页面的 bug", "write a unit test for the cookie parser",
                     "rotate our anthropic api keys every 90 days", "用 Claude API 写一个聊天机器人",
                     "distill this long article into three bullet points"]:
            with self.subTest(text=text):
                self.assertIsNone(prompt(text))

    def test_strict_blocks_and_warn_only_warns(self):
        self.assertEqual(prompt("怎么绕过 Claude 的 rate limit", "strict")["decision"], "block")
        self.assertNotIn("decision", prompt("怎么绕过 Claude 的 rate limit", "warn"))

    def test_allow_marker(self):
        self.assertIsNone(prompt("讲讲什么是 Claude 号池以及为什么违规 ac-good-boy:allow"))


class ToolTests(unittest.TestCase):
    def test_high_asks(self):
        out = bash("cat ~/.claude/.credentials.json")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_strict_denies(self):
        out = bash("mitmdump --mode transparent # capture claude traffic", "strict")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_medium_only_warns(self):
        out = run("tool", {"tool_name": "Write", "cwd": "/tmp", "tool_input": {
            "file_path": "/tmp/app.py", "content": 'KEY = "sk-ant-api03-' + "a" * 40 + '"'}})
        self.assertNotIn("permissionDecision", out["hookSpecificOutput"])
        self.assertIn("[R11]", out["systemMessage"])

    def test_clean_command(self):
        self.assertIsNone(bash("npm test && git status"))

    def test_ignore_file(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        out = run("tool", {"tool_name": "Write", "cwd": root, "tool_input": {
            "file_path": os.path.join(root, "README.md"), "content": "不要搞 Claude 号池"}})
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
