#!/usr/bin/env python3
"""
A 股智能分析 Agent — CLI 入口

用法:
    python main.py 600000              # 默认统计 60 天
    python main.py 600000 -d 120       # 统计 120 天
    python main.py sh.000001 -d 30     # 完整代码格式
    python main.py 600000 -o report.md # 输出到文件

环境变量:
    LLM_BASE_URL    LLM API 地址（默认 OpenAI）
    LLM_API_KEY     API 密钥
    LLM_MODEL       模型名称（默认 gpt-4o）
"""

import argparse
import asyncio
import logging
import sys
import os

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.orchestrator import StockAnalysisOrchestrator
from agent.data.fetcher import FetchError


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def main():
    parser = argparse.ArgumentParser(
        description="A 股智能分析 Agent — 基于 akshare + LLM 的技术分析报告生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py 600000               # 分析浦发银行，默认60天
  python main.py 000001 -d 30         # 分析平安银行，统计30天
  python main.py sh.688111 -d 90      # 分析金山办公，统计90天
  python main.py 300750 -o report.md  # 输出到文件
        """,
    )
    parser.add_argument("code", help="A 股代码，如 600000、sh.000001、sz.300750")
    parser.add_argument("-d", "--days", type=int, default=60, help="统计天数 (5~365，默认 60)")
    parser.add_argument("-o", "--output", type=str, default=None, help="输出到文件（默认输出到终端）")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if not os.getenv("LLM_API_KEY"):
        print("⚠️  未设置 LLM_API_KEY 环境变量，请先配置：")
        print("   export LLM_API_KEY='your-api-key'")
        print("   export LLM_BASE_URL='https://api.openai.com/v1'  # 可选，兼容 OpenAI/DeepSeek/Qwen 等")
        print("   export LLM_MODEL='gpt-4o'  # 可选")
        sys.exit(1)

    orchestrator = StockAnalysisOrchestrator()

    try:
        print(f"正在分析 {args.code}（最近 {args.days} 个交易日）...\n")
        report = await orchestrator.run(args.code, args.days)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"✅ 报告已保存到: {args.output}")
        else:
            print(report)

    except FetchError as e:
        print(f"❌ 数据拉取失败: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"❌ 输入参数错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 未知错误: {e}", file=sys.stderr)
        if args.verbose:
            raise
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
