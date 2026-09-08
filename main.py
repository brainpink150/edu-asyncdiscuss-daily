"""
教育技术学每日文献推送 —— 主入口

每天从 OpenAlex 检索中英两种语种、按 3:2 配额（外文 3 / 中文 2）、
按主题相关性排序后推送至邮箱。已推送的论文通过 history 持久化
避免跨日重复。
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

from src.fetchers.journals import (
    INTERNATIONAL_JOURNALS,
    DOMESTIC_JOURNALS,
    journal_lookup,
)
from src.fetchers import openalex, crossref
from src import history
from src.formatter import render_html, render_markdown
from src.notifier import send_email

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily")

# 配额配置：外文 3 篇 + 中文 2 篇
EN_QUOTA = int(os.getenv("EN_QUOTA", "3"))
ZH_QUOTA = int(os.getenv("ZH_QUOTA", "2"))


def _fetch_for_language(
    issns: list,
    lookback_days: int,
    quota: int,
    language: str,
    contact_email: str,
    pushed_set: set,
) -> list:
    """
    单语种抓取 + 标准化 + 历史过滤 + 排序 + 配额截取。

    候选池拉到 quota * 8，确保历史过滤后还有足够候选。
    """
    raw = openalex.fetch_recent_papers(
        issns=issns,
        lookback_days=lookback_days,
        per_page=max(quota * 8, 30),
        mailto=contact_email,
    )

    if not raw:
        logger.warning(f"[{language}] OpenAlex 无结果，尝试 Crossref 兜底")
        raw = crossref.fetch_recent_papers_crossref(
            issns=issns,
            lookback_days=lookback_days,
            rows=max(quota * 8, 30),
            mailto=contact_email,
        )

    if not raw:
        logger.warning(f"[{language}] 所有数据源均无结果")
        return []

    papers = [openalex.normalize_work(w) for w in raw]
    papers = openalex.deduplicate(papers)

    # 历史过滤：剔除最近已推过的
    before = len(papers)
    papers = [p for p in papers if not history.is_pushed(p, pushed_set)]
    logger.info(
        f"[{language}] 标准化 {before} → 历史过滤后 {len(papers)}"
    )

    if not papers:
        return []

    # 排序 + 截取
    ranked = openalex.rank_papers(papers, top_k=quota)
    logger.info(f"[{language}] 取 top {len(ranked)} / {quota} 配额")
    return ranked


def run_pipeline(lookback_days: int = None) -> dict:
    """
    完整流程：
    1. 加载推送历史
    2. 拉宽窗口到 60 天，候选池充足
    3. 中英分路抓取 + 历史过滤 + 配额
    4. 合并、格式化、推送
    5. 落盘 archive + 写入 history（Actions 会自动 commit 回仓库）
    """
    load_dotenv()

    # 拉宽窗口到 60 天，确保有足够候选
    lookback_days = int(lookback_days or os.getenv("LOOKBACK_DAYS", "60"))
    contact_email = os.getenv("CONTACT_EMAIL") or "daily-bot@example.com"

    # 1. 加载历史
    hist = history.load_history()
    pushed_set = history.get_pushed_set(hist)
    logger.info(f"历史已记录 {len(pushed_set)} 条论文标识")

    # 2. 中英分路抓取
    en_issns = [j["issn"] for j in INTERNATIONAL_JOURNALS]
    zh_issns = [j["issn"] for j in DOMESTIC_JOURNALS]

    en_papers = _fetch_for_language(
        en_issns, lookback_days, EN_QUOTA, "en", contact_email, pushed_set
    )
    zh_papers = _fetch_for_language(
        zh_issns, lookback_days, ZH_QUOTA, "zh", contact_email, pushed_set
    )

    # 3. 合并
    top_papers = en_papers + zh_papers
    logger.info(
        f"最终筛选：外文 {len(en_papers)} + 中文 {len(zh_papers)} = {len(top_papers)}"
    )

    if not top_papers:
        logger.warning("今日无可推送文献（中英都为空）")
        summary = {
            "date": datetime.now().isoformat(),
            "paper_count": 0,
            "en_count": 0,
            "zh_count": 0,
            "status": "no_results",
        }
        _write_summary(summary)
        return summary

    # 4. 格式化
    html_body = render_html(top_papers, lookback_days=lookback_days)
    md_body = render_markdown(top_papers, lookback_days=lookback_days)

    # 落盘 Markdown 归档
    archive_dir = Path("archive")
    archive_dir.mkdir(exist_ok=True)
    md_file = archive_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    md_file.write_text(md_body, encoding="utf-8")
    logger.info(f"Markdown 归档: {md_file}")

    # 5. 邮件推送
    today_str = datetime.now().strftime("%Y年%m月%d日")
    subject = f"[教育技术学·异步讨论] {today_str} · 外文 {len(en_papers)} + 中文 {len(zh_papers)}"
    sent = send_email(subject=subject, html_body=html_body, text_body=md_body)

    # 6. 更新历史（无论邮件成功失败都更新，避免失败重试时重复推）
    new_hist = history.add_papers(hist, top_papers)
    history.save_history(new_hist)

    summary = {
        "date": datetime.now().isoformat(),
        "paper_count": len(top_papers),
        "en_count": len(en_papers),
        "zh_count": len(zh_papers),
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
    sys.exit(0 if summary["status"] in ("sent", "no_results") else 1)
