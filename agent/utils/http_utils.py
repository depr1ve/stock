"""
编码安全的 HTTP 请求工具。
国内财经网站（东方财富、同花顺、证券时报等）常使用 GBK/GB2312 编码，
直接 response.text 假设 UTF-8 会导致乱码。通过 apparent_encoding 自动检测编码。
"""

import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_text(url: str, timeout: int = 10) -> Optional[str]:
    """
    编码安全的网页正文抓取。

    使用 requests 的 apparent_encoding 自动检测页面编码（底层调用 chardet），
    避免国内财经网站 GBK/GB2312 内容直接 .text 出现乱码。

    返回解码后的纯文本（已去除 HTML 标签），失败返回 None。
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.encoding = resp.apparent_encoding
        html = resp.text

        if not html:
            return None

        return _strip_html(html)

    except requests.RequestException as e:
        logger.warning("HTTP 请求失败 %s: %s", url, e)
        return None


def _strip_html(html: str) -> str:
    """去除 HTML 标签，提取纯文本，保留块级结构的换行"""
    # 块级元素前插入换行，便于后续提取段落
    for tag in ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'br']:
        html = re.sub(rf'</?{tag}[^>]*>', '\n', html, flags=re.IGNORECASE)
    # 移除 script / style 及内容
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # 移除剩余 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', text)
    # 解码 HTML 实体
    import html as _html
    text = _html.unescape(text)
    # 按行清理空白，保留换行
    lines = []
    for line in text.split('\n'):
        line = re.sub(r'\s+', ' ', line).strip()
        if line:
            lines.append(line)
    return '\n'.join(lines)


def summarize_text(text: str, max_chars: int = 500) -> str:
    """
    提取式摘要：从爬取的正文中提取关键段落。

    中文财经新闻遵循「倒金字塔」结构，关键信息在前几段。
    策略：跳过太短的行（导航/页脚噪音），取前几个有效段落。
    """
    if not text or len(text) <= max_chars:
        return text or ""

    # 按换行/句号/分号拆段落
    paragraphs = re.split(r'[\n\r。；;]', text)
    meaningful = []
    for p in paragraphs:
        p = p.strip()
        # 跳过太短的片段（导航文字、广告等）
        if len(p) >= 15:
            meaningful.append(p)

    if not meaningful:
        return text[:max_chars]

    # 按原文顺序取，截到 max_chars
    result = ""
    for p in meaningful:
        if len(result) + len(p) + 1 > max_chars:
            break
        result += p + "。"
    return result.strip()
