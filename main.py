"""
教育技术学每日文献推送 —— 主入口

每天从 OpenAlex / Crossref 检索近一周内、与"在线异步讨论"主题相关的
教育技术学权威期刊新文献，挑选 top-K 推送至邮箱。
"""

import logging
import os
import sys
import json
from datetime import datetime
from pathlib import Path

# 让脚本可以直接 `python main.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from src.fetchers.journals import get_issn_list
from src.fetchers import openalex, crossref
from src.formatter import render_html, render_markdown
from src.notifier import send_email

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily")


def run_pipeline(lookback_days: int = None, top_k: int = None) -> dict:
    """
    完整流程：检索 → 标准化 → 排序 → 格式化 → 发送邮件。

    返回运行摘要（供 Actions 落盘）。
    """
    # 加载 .env（本地运行时），GitHub Actions 会用 Secrets 注入环境变量
    load_dotenv()

    lookback_days = int(lookback_days or os.getenv("LOOKBACK_DAYS", "7"))
    top_k = int(top_k or os.getenv("DAILY_TOPK", "5"))
    contact_email = os.getenv("CONTACT_EMAIL") or "daily-bot@example.com"

    issns = get_issn_list()
    logger.info(f"共监控 {len(issns)} 本期刊")

    # 1. 主数据源：OpenAlex
    works_raw = openalex.fetch_recent_papers(
        issns=issns,
        lookback_days=lookback_days,
        per_page=top_k * 5,  # 多取一些，排序后再截
        mailto=contact_email,
    )

    # 2. 兜底数据源：Crossref（当 OpenAlex 返回 0 条时）
    source_used = "openalex"
    if not works_raw:
        logger.warning("OpenAlex 未返回结果，切换至 Crossref 兜底")
        source_used = "crossref"
        works_raw = crossref.fetch_recent_papers_crossref(
            issns=issns,
            lookback_days=lookback_days,
            rows=top_k * 5,
            mailto=contact_email,
        )

    if not works_raw:
        logger.warning("所有数据源均无结果，今天不发邮件")
        summary = {
            "date": datetime.now().isoformat(),
            "source": source_used,
            "paper_count": 0,
            "status": "no_results",
        }
        _write_summary(summary)
        return summary

    # 3. 标准化
    if source_used == "openalex":
        papers = [openalex.normalize_work(w) for w in works_raw]
    else:
        papers = [crossref.normalize_crossref_item(w) for w in works_raw]

    papers = openalex.deduplicate(papers)
    logger.info(f"标准化 + 去重后剩余 {len(papers)} 篇")

    # 4. 排序 + 截取
    top_papers = openalex.rank_papers(papers, top_k=top_k)
    logger.info(f"最终筛选 {len(top_papers)} 篇推送")

    # 5. 格式化
    html_body = render_html(top_papers, lookback_days=lookback_days)
    md_body = render_markdown(top_papers, lookback_days=lookback_days)

    # 落盘 Markdown，方便 GitHub Actions 保留历史归档
    archive_dir = Path("archive")
    archive_dir.mkdir(exist_ok=True)
    md_file = archive_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    md_file.write_text(md_body, encoding="utf-8")
    logger.info(f"Markdown 归档已写入 {md_file}")

    # 6. 邮件推送
    today_str = datetime.now().strftime("%Y年%m月%d日")
    subject = f"[教育技术学·异步讨论] {today_str} · {len(top_papers)} 篇新文献"
    sent = send_email(subject=subject, html_body=html_body, text_body=md_body)

    summary = {
        "date": datetime.now().isoformat(),
        "source": source_used,
        "paper_count": len(top_papers),
        "status": "sent" if sent else "send_failed",
        "subject": subject,
        "papers": [
            {"title": p.get("title"), "doi": p.get("doi"), "venue": p.get("venue")}
            for p in top_papers
        ],
    }
    _write_summary(summary)
    return summary


def _write_summary(summary: dict):
    """把运行摘要写到 logs/summary.json。"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    (log_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    summary = run_pipeline()
    logger.info(f"运行结束：{summary['status']}")
    # Actions 中通过退出码判断成败
    sys.exit(0 if summary["status"] in ("sent", "no_results") else 1)