"""
文献格式化模块：把内部标准化的 paper 字典渲染成 HTML / Markdown，
供邮件正文使用。
"""

from datetime import datetime
from typing import List, Dict
import html as html_lib


def render_html(papers: List[Dict], lookback_days: int = 7) -> str:
    """生成邮件 HTML 正文（适合在手机邮件客户端阅读）。"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    subtitle = f"近 {lookback_days} 天 · 教育技术学权威期刊"
    count = len(papers)

    html_parts = [
        '<!DOCTYPE html>',
        '<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>',
        '<body style="margin:0;padding:0;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;color:#1d1d1f;">',
        '<div style="max-width:680px;margin:0 auto;background:#ffffff;padding:24px 20px;">',
        # Header
        '<div style="border-bottom:2px solid #1d1d1f;padding-bottom:14px;margin-bottom:18px;">',
        f'  <h1 style="margin:0;font-size:20px;color:#1d1d1f;">📚 教育技术学每日文献推送</h1>',
        f'  <p style="margin:6px 0 0;font-size:13px;color:#6e6e73;">{subtitle} · {today_str}</p>',
        '</div>',
    ]

    if count == 0:
        html_parts.append(
            '<div style="padding:20px;background:#f5f5f7;border-radius:8px;text-align:center;color:#6e6e73;">'
            '今天暂无符合关键词的最新文献，明天继续。</div>'
        )
    else:
        html_parts.append(
            f'<p style="margin:0 0 16px;font-size:13px;color:#6e6e73;">'
            f'为今日筛选到 <strong style="color:#1d1d1f;">{count}</strong> 篇主题相关文献。</p>'
        )
        for idx, p in enumerate(papers, 1):
            html_parts.append(_paper_card_html(idx, p))

    html_parts.append(
        '<div style="margin-top:24px;padding-top:14px;border-top:1px solid #e5e5ea;font-size:11px;color:#86868b;line-height:1.6;">'
        '数据源：OpenAlex（https://openalex.org）与 Crossref，覆盖 SSCI 与 CSSCI 教育技术学权威期刊。'
        '<br>本项目开源，仅供学术研究使用，不构成任何建议。'
        '</div>'
        '</div></body></html>'
    )

    return "\n".join(html_parts)


def _paper_card_html(idx: int, p: Dict) -> str:
    title = html_lib.escape(p.get("title") or "(无标题)")
    authors = html_lib.escape(p.get("authors") or "佚名")
    venue = html_lib.escape(p.get("venue_full") or p.get("venue") or "")
    date = html_lib.escape(p.get("date") or "")
    abstract = html_lib.escape(p.get("abstract") or "暂无摘要")
    url = html_lib.escape(p.get("url") or "")
    doi = html_lib.escape(p.get("doi") or "")
    cited = p.get("cited_by_count", 0)
    keywords = p.get("keywords") or []
    lang_badge = "🇨🇳 中文" if p.get("language") == "zh" else "🇬🇧 英文"

    # 摘要截断到 350 字
    if len(abstract) > 350:
        abstract = abstract[:350].rstrip() + "…"

    kw_html = ""
    if keywords:
        kw_items = " ".join(
            f'<span style="display:inline-block;background:#f5f5f7;color:#1d1d1f;'
            f'padding:2px 8px;border-radius:10px;font-size:11px;margin:2px 2px 0 0;">'
            f'{html_lib.escape(k)}</span>'
            for k in keywords[:5]
        )
        kw_html = f'<div style="margin-top:8px;">{kw_items}</div>'

    link_html = ""
    if url:
        link_html = (
            f'<a href="{url}" style="display:inline-block;margin-top:8px;'
            f'color:#0066cc;text-decoration:none;font-size:13px;">'
            f'👉 阅读全文</a>'
        )
    doi_html = ""
    if doi:
        doi_html = (
            f'<span style="margin-left:10px;font-size:11px;color:#86868b;">'
            f'DOI: {doi}</span>'
        )

    return f"""
<div style="margin-bottom:18px;padding:14px 16px;background:#fbfbfd;border:1px solid #e5e5ea;border-radius:10px;">
  <div style="display:flex;align-items:center;margin-bottom:6px;">
    <span style="display:inline-block;background:#1d1d1f;color:#ffffff;font-size:11px;font-weight:bold;padding:2px 8px;border-radius:10px;margin-right:8px;">#{idx}</span>
    <span style="font-size:11px;color:#86868b;">{lang_badge} · {date}</span>
  </div>
  <h2 style="margin:4px 0;font-size:16px;line-height:1.45;color:#1d1d1f;">{title}</h2>
  <p style="margin:4px 0;font-size:12px;color:#6e6e73;"><strong>作者：</strong>{authors}</p>
  <p style="margin:4px 0;font-size:12px;color:#6e6e73;"><strong>期刊：</strong>{venue}</p>
  <p style="margin:8px 0 0;font-size:13px;line-height:1.6;color:#1d1d1f;">{abstract}</p>
  {kw_html}
  <div style="margin-top:6px;">
    {link_html}
    {doi_html}
    <span style="margin-left:10px;font-size:11px;color:#86868b;">引用：{cited}</span>
  </div>
</div>
""".strip()


def render_markdown(papers: List[Dict], lookback_days: int = 7) -> str:
    """生成 Markdown 版本（调试 / 归档用）。"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# 📚 教育技术学每日文献推送",
        f"> {today_str} · 近 {lookback_days} 天 · 教育技术学权威期刊",
        "",
    ]
    if not papers:
        lines.append("今天暂无符合关键词的最新文献，明天继续。")
        return "\n".join(lines)

    lines.append(f"为今日筛选到 **{len(papers)}** 篇主题相关文献。\n")
    for idx, p in enumerate(papers, 1):
        lang = "🇨🇳 中文" if p.get("language") == "zh" else "🇬🇧 英文"
        lines.append(f"## #{idx} {p.get('title','')}")
        lines.append(f"**{lang}** · {p.get('date','')}  ")
        lines.append(f"- 作者：{p.get('authors','佚名')}")
        lines.append(f"- 期刊：{p.get('venue_full','')}（{p.get('venue','')}）")
        lines.append(f"- 引用数：{p.get('cited_by_count',0)}")
        if p.get("keywords"):
            lines.append(f"- 关键词：{', '.join(p['keywords'])}")
        if p.get("doi"):
            lines.append(f"- DOI：`{p['doi']}`")
        if p.get("url"):
            lines.append(f"- 链接：{p['url']}")
        abstract = p.get("abstract", "")
        if abstract:
            if len(abstract) > 400:
                abstract = abstract[:400].rstrip() + "…"
            lines.append("")
            lines.append(f"> {abstract}")
        lines.append("\n---\n")

    return "\n".join(lines)