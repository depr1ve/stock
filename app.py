#!/usr/bin/env python3
"""
A 股智能分析 — 交互式 CLI
基于 rich 构建，支持实时进度、彩色报告、历史记录、配置管理。
"""

import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.live import Live
from rich import box

from agent.orchestrator import StockAnalysisOrchestrator
from agent.data.fetcher import FetchError
from agent.models.schemas import StockRequest

# ── 主题配色 ──────────────────────────────────────────────

APP_THEME = Theme({
    "title": "bold bright_cyan",
    "subtitle": "dim white",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "highlight": "bold cyan",
    "number.up": "bold red",
    "number.down": "bold green",
    "number.neutral": "white",
    "label": "dim cyan",
    "menu.key": "bold bright_cyan",
})

console = Console(theme=APP_THEME)

# 历史记录目录
HISTORY_DIR = Path(__file__).parent / "history"
HISTORY_DIR.mkdir(exist_ok=True)

# 配置文件
CONFIG_FILE = Path(__file__).parent / ".env"

# ── 工具函数 ──────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def color_change(val: float) -> str:
    """根据正负返回 rich 风格的标记"""
    if val > 0:
        return f"[number.up]{val:+.2f}%[/]"
    elif val < 0:
        return f"[number.down]{val:+.2f}%[/]"
    return f"[number.neutral]{val:+.2f}%[/]"


def fmt_num(val, decimals: int = 2) -> str:
    """安全格式化数字，None → N/A"""
    if val is None:
        return "[dim]N/A[/]"
    import math
    try:
        if math.isnan(val):
            return "[dim]N/A[/]"
    except Exception:
        pass
    return f"{val:.{decimals}f}"


# ── 主菜单 ────────────────────────────────────────────────

def show_banner():
    banner = r"""
  [title]╔══════════════════════════════════════╗[/]
  [title]║[/]       [title]A 股智能分析 Agent[/]           [title]║[/]
  [title]╚══════════════════════════════════════╝[/]
"""
    console.print(banner)
    console.print("  [dim]基于 akshare + LLM 的技术分析报告系统[/]\n")


def main_menu() -> str:
    """主菜单，返回选项"""
    menu = Table(show_header=False, box=box.SIMPLE, padding=(0, 4))
    menu.add_column("key", style="menu.key", width=6)
    menu.add_column("desc", style="white")
    menu.add_row("[1]", "开始新分析")
    menu.add_row("[2]", "历史报告")
    menu.add_row("[3]", "系统配置")
    menu.add_row("[0]", "退出")
    console.print(Panel(menu, title="主菜单", border_style="cyan", padding=(1, 2)))
    return Prompt.ask("\n  请选择", choices=["0", "1", "2", "3"], default="1")


# ── 配置管理页 ────────────────────────────────────────────

def config_page():
    """编辑 .env 配置"""
    clear()
    console.print(Panel("[title]系统配置[/]", border_style="cyan"))
    console.print()

    # 读取当前配置
    config = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()

    table = Table(title="当前配置", box=box.ROUNDED, border_style="dim cyan")
    table.add_column("配置项", style="label")
    table.add_column("值", style="white")

    defaults = {
        "LLM_BASE_URL": "https://api.openai.com/v1",
        "LLM_API_KEY": "(未设置)",
        "LLM_MODEL": "gpt-4o",
    }

    for key, default in defaults.items():
        val = config.get(key, default)
        if key == "LLM_API_KEY" and val != "(未设置)" and len(val) > 12:
            val = val[:8] + "..." + val[-4:]
        table.add_row(key, val)

    console.print(table)
    console.print()

    if Confirm.ask("\n  是否修改配置", default=False):
        console.print("\n[dim]（输入新值直接回车，留空表示不修改）[/]\n")
        new_vals = {}
        for key, default in defaults.items():
            current = config.get(key, "")
            prompt = f"  {key}"
            if key == "LLM_API_KEY" and current:
                prompt += f" [当前: {current[:8]}...{current[-4:]}]"
            elif current:
                prompt += f" [当前: {current}]"
            val = Prompt.ask(prompt, default="")
            if val.strip():
                new_vals[key] = val.strip()

        if new_vals:
            # 保留未修改的
            for k, v in config.items():
                if k not in new_vals:
                    new_vals[k] = v
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                for k, v in new_vals.items():
                    f.write(f"{k}={v}\n")
            console.print("\n[success]配置已保存[/]\n")
        else:
            console.print("\n[dim]未做修改[/]\n")

    Prompt.ask("\n  按回车返回主菜单", default="")


# ── 分析流程 ──────────────────────────────────────────────

async def run_analysis(stock_code: str, days: int):
    """执行完整分析流水线，返回 report 文本"""
    orchestrator = StockAnalysisOrchestrator()
    return await orchestrator.run(stock_code, days)


def analysis_page():
    """分析输入页 → 进度 → 结果展示"""
    clear()
    console.print(Panel("[title]开始新分析[/]", border_style="cyan"))
    console.print()

    # 快速选择
    console.print("  [dim]常用标的快速选择:[/]")
    quick = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    quick.add_column("k", style="menu.key")
    quick.add_column("d")
    quick.add_column("k2", style="menu.key")
    quick.add_column("d2")
    quick.add_row("[1]", "浦发银行 600000", "[4]", "宁德时代 300750")
    quick.add_row("[2]", "平安银行 000001", "[5]", "贵州茅台 600519")
    quick.add_row("[3]", "金山办公 688111", "[6]", "自定义输入")
    console.print(quick)
    console.print()

    choice = Prompt.ask("  选择标的", choices=["1", "2", "3", "4", "5", "6"], default="1")
    presets = {
        "1": ("600000", "浦发银行"),
        "2": ("000001", "平安银行"),
        "3": ("sh.688111", "金山办公"),
        "4": ("300750", "宁德时代"),
        "5": ("600519", "贵州茅台"),
    }

    if choice == "6":
        stock_code = Prompt.ask("  输入股票代码", default="600000")
        try:
            StockRequest(raw_code=stock_code, days=60)
        except ValueError as e:
            console.print(f"[error]代码格式错误: {e}[/]")
            Prompt.ask("\n  按回车返回主菜单", default="")
            return
    else:
        stock_code = presets[choice][0]

    days = IntPrompt.ask("  统计天数 (5-365)", default=60, choices=[str(i) for i in range(5, 366)])

    console.print()
    console.print(f"  [dim]即将分析[/] [highlight]{stock_code}[/] [dim]，统计最近[/] [highlight]{days}[/] [dim]天[/]")
    if not Confirm.ask("\n  确认开始分析", default=True):
        return

    # ── 进度条阶段 ──────────────────────────────────────
    console.print()
    report = None

    with Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("{task.percentage:.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]正在拉取行情数据...", total=100)

        try:
            # 实际工作在线程中执行
            progress.update(task, description="[cyan]正在拉取行情数据...", advance=10)
            report = asyncio.run(run_analysis(stock_code, days))
            progress.update(task, description="[cyan]分析完成", completed=100)
        except FetchError as e:
            progress.update(task, description="[error]数据拉取失败[/]", completed=0)
            console.print(f"\n[error]❌ {e}[/]")
            if not os.getenv("LLM_API_KEY"):
                console.print("[warning]提示: 请先配置 LLM_API_KEY (主菜单 → 系统配置)[/]")
            Prompt.ask("\n  按回车返回主菜单", default="")
            return
        except Exception as e:
            progress.update(task, description="[error]分析失败[/]", completed=0)
            console.print(f"\n[error]❌ {e}[/]")
            if not os.getenv("LLM_API_KEY"):
                console.print("[warning]提示: 请先配置 LLM_API_KEY (主菜单 → 系统配置)[/]")
            Prompt.ask("\n  按回车返回主菜单", default="")
            return

    # ── 结果展示 ────────────────────────────────────────
    console.print()
    if report:
        # 用 rich Markdown 渲染
        md = Markdown(report)
        console.print(Panel(md, title="分析报告", border_style="green", padding=(1, 2)))

        # 保存历史
        if Confirm.ask("\n  是否保存报告到历史记录", default=True):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"{stock_code.replace('.', '_')}_{timestamp}.md"
            fpath = HISTORY_DIR / fname
            fpath.write_text(report, encoding="utf-8")
            console.print(f"[success]已保存: history/{fname}[/]")

        # 导出
        if Confirm.ask("  是否导出到指定路径", default=False):
            out = Prompt.ask("  输出文件路径", default=f"report_{stock_code.replace('.','_')}_{date.today()}.md")
            Path(out).write_text(report, encoding="utf-8")
            console.print(f"[success]已导出: {out}[/]")

    Prompt.ask("\n  按回车返回主菜单", default="")


# ── 历史记录页 ────────────────────────────────────────────

def history_page():
    """查看历史报告"""
    clear()
    console.print(Panel("[title]历史报告[/]", border_style="cyan"))
    console.print()

    files = sorted(HISTORY_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        console.print("  [dim]暂无历史报告[/]")
        Prompt.ask("\n  按回车返回主菜单", default="")
        return

    table = Table(box=box.ROUNDED, border_style="dim cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("股票")
    table.add_column("时间")
    table.add_column("文件名", style="dim")

    for i, f in enumerate(files[:20], 1):
        name = f.stem
        # 解析文件名: sh_600000_20260520_120000
        parts = name.split("_")
        code = "_".join(parts[:-2]) if len(parts) >= 3 else name
        ts = parts[-2] + "_" + parts[-1] if len(parts) >= 3 else ""
        ts_display = f"{ts[:4]}-{ts[4:6]}-{ts[6:11]}:{ts[11:13]}:{ts[13:15]}" if len(ts) == 15 else ts
        table.add_row(str(i), code.replace("_", "."), ts_display, f.name)

    console.print(table)
    console.print()

    choice = Prompt.ask("  输入序号查看详情 (0返回)", default="0")
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(files):
            content = files[idx - 1].read_text(encoding="utf-8")
            console.print()
            console.print(Panel(Markdown(content), border_style="green", padding=(1, 2)))
            Prompt.ask("\n  按回车返回", default="")

    history_page() if choice != "0" else None


# ── 入口 ─────────────────────────────────────────────────

def main():
    # 加载 .env
    from dotenv import load_dotenv
    load_dotenv(CONFIG_FILE)

    while True:
        clear()
        show_banner()
        choice = main_menu()

        if choice == "0":
            clear()
            console.print("[dim]再见[/]\n")
            break
        elif choice == "1":
            analysis_page()
        elif choice == "2":
            history_page()
        elif choice == "3":
            config_page()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]已退出[/]")
        sys.exit(0)
