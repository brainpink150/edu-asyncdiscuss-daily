"""
本地测试脚本：只验证 OpenAlex 检索 + 格式化，不发邮件。

运行：python scripts/test_local.py
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fetchers.journals import get_issn_list
from src.fetchers import openalex, crossref
from src.formatter import render_html, render_markdown


def main():
    issns = get_issn_list()
    print(f"📚 监控期刊数：{len(issns)}")
    print(f"📋 ISSN 列表：{issn_list_summary()}")
    print()

    # 测试 OpenAlex
    print("🔍 测试 OpenAlex 检索...")
    works = openalex.fetch_recent_papers(
        issns=issns,
        lookback_days=30,  # 测试时拉长窗口，确保有数据
        per_page=15,
    )

    if not works:
        print("⚠️ OpenAlex 返回 0 条，测试 Crossref 兜底...")
        items = crossref.fetch_recent_papers_crossref(
            issns=issns,
            lookback_days=30,
            rows=15,
        )
        if not items:
            print("❌ 两个数据源都没结果，可能是网络问题或 ISSN 写法不规范")
            return 1
        papers = [crossref.normalize_crossref_item(it) for it in items]
    else:
        papers = [openalex.normalize_work(w) for w in works]

    papers = openalex.deduplicate(papers)
    top_papers = openalex.rank_papers(papers, top_k=5)

    print(f"\n✅ 检索到 {len(papers)} 篇 → 排序后取 {len(top_papers)} 篇\n")

    for i, p in enumerate(top_papers, 1):
        print(f"--- 第 {i} 篇 ---")
        print(f"标题：{p.get('title','')[:80]}")
        print(f"作者：{p.get('authors','')[:80]}")
        print(f"期刊：{p.get('venue_full','')}")
        print(f"日期：{p.get('date','')}")
        print(f"DOI：{p.get('doi','')}")
        print(f"摘要：{(p.get('abstract','') or '无')[:150]}...")
        print()

    # 保存 HTML 和 Markdown 预览
    out_dir = Path(__file__).resolve().parent.parent / "test_output"
    if not out_dir.exists():
        out_dir.mkdir()
    html_body = render_html(top_papers, lookback_days=30)
    md_body = render_markdown(top_papers, lookback_days=30)

    out_dir.joinpath("preview.html").write_text(html_body, encoding="utf-8")
    out_dir.joinpath("preview.md").write_text(md_body, encoding="utf-8")

    print(f"📄 预览已生成：{out_dir}")
    print(f"  - preview.html （浏览器打开看样式）")
    print(f"  - preview.md   （纯文本版）")
    print()
    print("💡 邮件不会真的发出，只验证检索链路。")

    return 0


def issn_list_summary():
    from src.fetchers.journals import ALL_JOURNALS
    return " / ".join(j["abbr"] for j in ALL_JOURNALS)


if __name__ == "__main__":
    sys.exit(main())