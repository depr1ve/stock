#!/usr/bin/env python3
"""
A 股智能分析 Agent — CLI 入口

用法:
    python -m agent.cli 600000              # 默认统计 60 天
    python -m agent.cli 600000 -d 120       # 统计 120 天
    python -m agent.cli sh.000001 -d 30     # 完整代码格式
    python -m agent.cli 600000 -o report.md # 输出到文件
"""

import argparse
import asyncio
import logging
import sys
import os

from dotenv import load_dotenv
load_dotenv()

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
    parser = argparse.ArgumentParser(description="A 股智能分析 Agent")
    parser.add_argument("code", help="A 股代码，如 600000、sh.000001")
    parser.add_argument("-d", "--days", type=int, default=60, help="统计天数 (5~365，默认 60)")
    parser.add_argument("-o", "--output", type=str, default=None, help="输出到文件")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if not os.getenv("LLM_API_KEY"):
        print("未设置 LLM_API_KEY 环境变量")
        sys.exit(1)

    orchestrator = StockAnalysisOrchestrator()
    try:
        print(f"正在分析 {args.code}（最近 {args.days} 个交易日）...\n")
        report = await orchestrator.run(args.code, args.days)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"报告已保存到: {args.output}")
        else:
            print(report)
    except FetchError as e:
        print(f"数据拉取失败: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"输入参数错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
