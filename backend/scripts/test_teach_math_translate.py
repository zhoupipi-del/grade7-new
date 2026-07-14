#!/usr/bin/env python3
"""
test_teach_math_translate.py — 审题助手 DeepSeek 翻译质量验证脚本

从 .env 读取 LLM 配置，用 8 道不同类型的初二数学应用题测试翻译效果。
用法: cd backend && .venv/bin/python scripts/test_teach_math_translate.py
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import httpx

# ── 从 .env 加载配置 ──────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

if not ENV_FILE.exists():
    print(f"[ERROR] .env 文件不存在: {ENV_FILE}")
    sys.exit(1)

# 简易 .env 解析（避免依赖 python-dotenv）
for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, val = line.partition("=")
    key, val = key.strip(), val.strip().strip('"').strip("'")
    if key and key not in os.environ:
        os.environ[key] = val

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

if not LLM_API_KEY:
    print("[ERROR] LLM_API_KEY 为空，请检查 .env 文件")
    sys.exit(1)

# ── 系统 Prompt（与 services.py 完全一致）────
SYSTEM_PROMPT = """你是初中数学老师，专门训练学生把应用题"翻译"成数学表达式。

核心规则：
1. 把题目拆成逐句（按逗号/句号分句）
2. 每句话翻译成一个或多个数学表达式，用中文单字变量（明、红、长、宽、速、时 等）
3. 解释为什么这样翻译——用初二学生能听懂的语言
4. 翻译完列出所有变量及其含义
5. 如果某句话只是背景描述（不包含数学关系），标记为"上下文"并跳过翻译
6. 必须用标准数学符号：=、+、-、×、÷、()、≥、≤

示例：
题目：小明比小红大3岁，5年后两人年龄之和是45岁，求小明今年几岁？

翻译：
- "小明比小红大3岁" → 明 = 红 + 3（小明的年龄 = 小红的年龄 + 3）
- "5年后两人年龄之和是45岁" → (明 + 5) + (红 + 5) = 45（5年后的年龄 = 当前年龄 + 5，再相加等于45）
- 变量：明 = 小明今年的年龄，红 = 小红今年的年龄

请严格按照以下 JSON 格式返回，不要输出任何其他内容：
{
  "translations": [
    {
      "sentence": "原句文本",
      "math_expression": "数学表达式",
      "explanation": "翻译解释（面向学生）"
    }
  ],
  "suggested_variables": {
    "变量名": "含义说明"
  }
}"""

# ── 8 道测试题（覆盖初二主要应用题类型）────
TEST_CASES = [
    {
        "title": "年龄问题",
        "question": "小明和小红今年共30岁，5年前小明的年龄是小红的4倍，求两人今年各几岁？",
        "grade": "初二上",
    },
    {
        "title": "行程问题 (相遇)",
        "question": "甲、乙两人从相距100千米的两地同时出发相向而行，甲每小时走6千米，乙每小时走4千米，问几小时后两人相遇？",
        "grade": "初二上",
    },
    {
        "title": "行程问题 (追及)",
        "question": "小王以每秒3米的速度向前走，小李从后面以每秒5米的速度追他，两人相距200米，问几秒后追上？",
        "grade": "初二上",
    },
    {
        "title": "工程问题",
        "question": "一项工程，甲单独做需要12天完成，乙单独做需要18天完成，两人合作需要几天完成？",
        "grade": "初二下",
    },
    {
        "title": "数字问题",
        "question": "一个两位数，个位数字比十位数字大3，把它的个位与十位数字交换后所得的新数比原数大27，求原两位数。",
        "grade": "初二上",
    },
    {
        "title": "几何面积问题",
        "question": "一个长方形的周长是36厘米，长比宽多2厘米，求这个长方形的面积。",
        "grade": "初二上",
    },
    {
        "title": "浓度问题",
        "question": "有浓度为20%的盐水300克，要把它稀释成浓度为5%的盐水，需要加水多少克？",
        "grade": "初二下",
    },
    {
        "title": "利润问题",
        "question": "某商店将进价为50元的商品按标价打8折出售，仍可获利10元，求该商品的标价。",
        "grade": "初二上",
    },
]

# ── ANSI 颜色 ─────────────────────────────────
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"


def call_deepseek(prompt: str, system_prompt: str, timeout: int = 60):
    """调用 DeepSeek API"""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                LLM_API_URL,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3,
                    "max_tokens": 4096,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content), None, resp.elapsed.total_seconds()
    except httpx.HTTPStatusError as e:
        return {}, f"HTTP {e.response.status_code}: {e.response.text[:200]}", 0
    except httpx.TimeoutException:
        return {}, "请求超时（60秒）", 60
    except json.JSONDecodeError as e:
        return {}, f"JSON 解析失败: {e}", 0
    except Exception as e:
        return {}, f"未知错误: {e}", 0


def print_translation(case_title: str, question: str, result: dict, elapsed: float):
    """美化打印翻译结果"""
    border = "─" * 64
    print(f"\n{C_BOLD}{C_CYAN}{border}{C_RESET}")
    print(f"{C_BOLD}【{case_title}】{C_RESET}  ⏱ {elapsed:.1f}s")
    print(f"{C_YELLOW}{question}{C_RESET}")
    print(f"{C_CYAN}{border}{C_RESET}")

    translations = result.get("translations", [])
    variables = result.get("suggested_variables", {})

    if not translations:
        print(f"{C_RED}  ⚠ 翻译结果为空{C_RESET}")
        return

    for i, t in enumerate(translations, 1):
        sentence = t.get("sentence", "")
        expr = t.get("math_expression", "")
        explanation = t.get("explanation", "")

        if expr in ("(上下文，无数学关系)", "（上下文）", "(上下文)"):
            print(f"\n  {C_MAGENTA}📖 [{i}] {sentence}{C_RESET}")
            print(f"     {C_MAGENTA}  ↳ (上下文描述，无需翻译){C_RESET}")
        else:
            print(f"\n  {C_GREEN}📐 [{i}] {sentence}{C_RESET}")
            print(f"     {C_BOLD}→ {expr}{C_RESET}")
            wrapper = textwrap.TextWrapper(
                width=56, initial_indent="     💬 ", subsequent_indent="        "
            )
            print(f"{C_CYAN}{wrapper.fill(explanation)}{C_RESET}")

    # 变量汇总
    if variables:
        print(f"\n  {C_YELLOW}📋 变量汇总:{C_RESET}")
        for var_name, meaning in variables.items():
            print(f"     {C_BOLD}{var_name}{C_RESET} = {meaning}")

    # 质量评分（简单启发式）
    quality = _evaluate_quality(translations, variables)
    print(f"\n  {C_CYAN}📊 质量检查:{C_RESET} {quality}")


def _evaluate_quality(translations: list, variables: dict) -> str:
    """简单质量检查"""
    checks = []
    total = 4

    # 检查1：是否有逐句拆分
    if len(translations) >= 2:
        checks.append(f"{C_GREEN}✓{C_RESET} 逐句拆分 ({len(translations)}句)")
    else:
        checks.append(f"{C_RED}✗{C_RESET} 未被逐句拆分")

    # 检查2：是否有数学表达式
    has_math = any(
        any(sym in t.get("math_expression", "") for sym in ["=", "+", "-", "×", "÷", "≤", "≥"])
        for t in translations
    )
    if has_math:
        checks.append(f"{C_GREEN}✓{C_RESET} 含数学符号")
    else:
        checks.append(f"{C_RED}✗{C_RESET} 缺数学符号")

    # 检查3：是否有变量定义
    if len(variables) >= 1:
        checks.append(f"{C_GREEN}✓{C_RESET} 变量定义 ({len(variables)}个)")
    else:
        checks.append(f"{C_YELLOW}△{C_RESET} 无变量定义")

    # 检查4：是否有中文单字变量
    has_single_char = any(len(k) == 1 for k in variables.keys())
    if has_single_char:
        checks.append(f"{C_GREEN}✓{C_RESET} 使用单字变量")
    else:
        checks.append(f"{C_YELLOW}△{C_RESET} 未用单字变量")

    score = sum(1 for c in checks if c.startswith(f"{C_GREEN}✓"))
    return f"{' | '.join(checks)}  [得分: {score}/{total}]"


def main():
    print(f"{C_BOLD}{'═' * 64}{C_RESET}")
    print(f"{C_BOLD}  审题助手 — DeepSeek 翻译质量验证{C_RESET}")
    print(f"{C_BOLD}  模型: {LLM_MODEL} | 测试题: {len(TEST_CASES)} 道{C_RESET}")
    print(f"{C_BOLD}{'═' * 64}{C_RESET}")

    success_count = 0
    total_elapsed = 0.0

    for i, case in enumerate(TEST_CASES, 1):
        user_prompt = f"题目：{case['question']}\n年级：{case['grade']}"

        print(f"\n  [{i}/{len(TEST_CASES)}] 正在翻译: {case['title']}...", end=" ", flush=True)

        result, error, elapsed = call_deepseek(user_prompt, SYSTEM_PROMPT)

        if error:
            print(f"{C_RED}失败: {error}{C_RESET}")
            continue

        success_count += 1
        total_elapsed += elapsed

        # 美化打印
        print_translation(case["title"], case["question"], result, elapsed)

    # ── 总结 ────────────────────────────────────
    avg_time = total_elapsed / success_count if success_count else 0
    print(f"\n\n{C_BOLD}{'═' * 64}{C_RESET}")
    print(f"{C_BOLD}  总结{C_RESET}")
    print(f"  {C_GREEN}成功{C_RESET}: {success_count}/{len(TEST_CASES)}")
    print(f"  {C_GREEN}总耗时{C_RESET}: {total_elapsed:.1f}s")
    print(f"  {C_GREEN}平均耗时{C_RESET}: {avg_time:.1f}s/题")
    print(f"{C_BOLD}{'═' * 64}{C_RESET}")

    if success_count == len(TEST_CASES):
        print(f"\n  {C_GREEN}✓ 全部通过！审题翻译 Prompt 质量达标{C_RESET}")
    else:
        print(f"\n  {C_YELLOW}△ 部分失败，请检查 DeepSeek API 配置{C_RESET}")

    return 0 if success_count == len(TEST_CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
