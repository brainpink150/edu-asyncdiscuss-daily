"""
教育技术学每日文献推送 —— 主入口

每天从 OpenAlex / Crossref 检索中英两种语种的文献，
按"外文 3 + 中文 2"配额组合，经历史去重后推送至邮箱。

如果中文期刊数据源不足，会自动：
1. 用更宽关键词 + 更长时间窗口再试一次
2. 仍不足时，用高相关外文候选补齐到 5 篇（日志会写明）
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

from src.fetchers.journals import INTERNATIONAL_JOURNALS, DOMESTIC_JOURNALS
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
# 中文源说明（2026-09-16 实测）：
#   OpenAlex 对 CSSCI 核心刊（电化教育研究 / 中国远程教育 / 开放教育研究等）
#   的索引停在 2020 年，近 5 年无数据；不限期刊搜中文关键词又全是水刊。
#   因此默认关闭中文配额（ZH_QUOTA=0），改推 5 篇外文。
#   日后若接入万方 / CNKI 开放 API，把 ZH_QUOTA 设回 2、EN_QUOTA 设回 3 即可。
EN_QUOTA = int(os.getenv("EN_QUOTA", "5"))
ZH_QUOTA = int(os.getenv("ZH_QUOTA", "0"))
TOTAL_TARGET = EN_QUOTA + ZH_QUOTA

# OpenAlex 查询用 "|" 做 OR
#
# 2026-09-16 实测：原「异步讨论」窄主题在 10 本顶刊 60 天窗口只有 27 条候选，
# 每天 5 篇 6 天就推完导致断流。放宽到教育技术学大类后：
#   宽关键词 + 60 天  -> 61 条
#   宽关键词 + 180 天 -> 183 条
#   宽关键词 + 365 天 -> 408 条
# 故这里放宽主题并把默认窗口设为 365 天。
EN_QUERY = "|".join([
    "online learning",
    "blended learning",
    "learning analytics",
    "educational technology",
    "MOOC",
    "online discussion",
    "asynchronous discussion",
    "computer-supported collaborative learning",
    "self-regulated learning",
    "flipped classroom",
])

ZH_QUERY = "|".join([
    "异步讨论",
    "在线讨论",
    "在线异步讨论",
    "异步在线讨论",
    "讨论论坛",
    "网络讨论",
    "计算机中介讨论",
])

# 中文兜底：更宽的关键词 + 更长的窗口，尽量保证 2 篇
BROADER_ZH_QUERY = "|".join([
    "在线学习", "网络学习", "远程教育", "开放教育", "教育技术",
    "信息化教学", "混合式教学", "慕课", "MOOC", "学习分析",
    "异步交互", "在线交互",
])

# 经典回顾：候选池耗尽时，从已推送历史挑高引文献（0 = 关闭）
CLASSIC_FALLBACK = int(os.getenv("CLASSIC_FALLBACK", "3"))


def _to_crossref_query(openalex_query: str) -> str:
    """Crossref 的 query.bibliographic 用 'OR' 而不是 '|'。"""
    return openalex_query.replace("|", " OR ")


def _try_fetch(
    issns: list,
    lookback_days: int,
    quota: int,
    language: str,
    contact_email: str,
    pushed_set: set,
    query: str,
) -> tuple[list, list]:
    """
    单次抓取尝试：OpenAlex → Crossref → 标准化 → 历史过滤 → 排序。

    返回 (selected, pool)：
    - selected: 已截取的 top 配额
    - pool: 完整候选池（用于后续补位）
    """
    # per_page 拉到 OpenAlex 单页上限 200。
    # 之前 30 太小：按日期倒序取回的最新 30 条大多是已推过的，
    # 历史过滤后只剩 13 篇，仍会很快断流。
    per_page = int(os.getenv("PER_PAGE", "200"))

    raw = openalex.fetch_recent_papers(
        issns=issns,
        lookback_days=lookback_days,
        per_page=per_page,
        mailto=contact_email,
        query=query,
    )

    if not raw:
        logger.warning(f"[{language}] OpenAlex 无结果，尝试 Crossref 兜底")
        raw = crossref.fetch_recent_papers_crossref(
            issns=issns,
            lookback_days=lookback_days,
            rows=max(quota * 8, 30),
            mailto=contact_email,
            query=_to_crossref_query(query),
        )

    if not raw:
        logger.warning(f"[{language}] 本次尝试所有数据源均无结果")
        return [], []

    papers = [openalex.normalize_work(w) for w in raw]
    papers = openalex.deduplicate(papers)

    before = len(papers)
    papers = [p for p in papers if not history.is_pushed(p, pushed_set)]
    logger.info(f"[{language}] 标准化 {before} → 历史过滤后 {len(papers)}")

    if not papers:
        return [], []

    ranked = openalex.rank_papers(papers, top_k=max(quota, len(papers)))
    selected = ranked[:quota]
    logger.info(f"[{language}] 本次取 top {len(selected)} / {quota} 配额")
    return selected, ranked


def _merge_unique(base: list, extra: list) -> list:
    """合并两个列表，按 DOI/标题指纹去重，保留 base 中的顺序。"""
    seen = set()
    result = []
    for p in base + extra:
        doi = (p.get("doi") or "").lower().strip()
        fp = history._title_fingerprint(p.get("title", ""))
        key = doi or fp
        if key and key not in seen:
            seen.add(key)
            result.append(p)
    return result


def _fetch_for_language(
    issns: list,
    lookback_days: int,
    quota: int,
    language: str,
    contact_email: str,
    pushed_set: set,
    query: str,
    fallback_query: str = None,
) -> tuple[list, list]:
    """
    带兜底策略的单语种抓取。

    1. 先用精准关键词 + lookback_days 抓取
    2. 如果不够配额，用 fallback_query + 2 倍窗口再试
    返回 (selected, pool)
    """
    selected, pool = _try_fetch(
        issns, lookback_days, quota, language, contact_email, pushed_set, query
    )

    if len(selected) < quota and fallback_query:
        need = quota - len(selected)
        logger.info(
            f"[{language}] 精准关键词不足，启用兜底查询，还需 {need} 篇"
        )
        extra_selected, extra_pool = _try_fetch(
            issns,
            lookback_days * 2,
            need,
            language,
            contact_email,
            pushed_set,
            fallback_query,
        )
        selected = _merge_unique(selected, extra_selected)
        pool = _merge_unique(pool, extra_pool)
        logger.info(
            f"[{language}] 兜底后共 {len(selected)} / {quota} 篇"
        )

    return selected, pool


def run_pipeline(lookback_days: int = None) -> dict:
    """
    完整流程：
    1. 加载推送历史
    2. 中英分路抓取（含中文兜底）
    3. 中文不足时，用外文候选补齐到目标总数
    4. 候选全部耗尽时，改用「经典高引回顾」兜底，不静默
    5. 格式化、推送、更新历史
    """
    load_dotenv()

    # 365 天窗口：实测宽关键词下 408 条候选，避免像 60 天那样 6 天推完断流
    lookback_days = int(lookback_days or os.getenv("LOOKBACK_DAYS", "365"))
    contact_email = os.getenv("CONTACT_EMAIL") or "daily-bot@example.com"

    # 1. 加载历史
    hist = history.load_history()
    pushed_set = history.get_pushed_set(hist)
    logger.info(f"历史已记录 {len(pushed_set)} 条论文标识")

    # 2. 中英分路抓取
    en_issns = [j["issn"] for j in INTERNATIONAL_JOURNALS]
    zh_issns = [j["issn"] for j in DOMESTIC_JOURNALS]

    en_selected, en_pool = _fetch_for_language(
        en_issns, lookback_days, EN_QUOTA, "en", contact_email, pushed_set, EN_QUERY
    )

    # 中文配额为 0 时直接跳过，省掉一次必定失败的 Crossref 请求（约 30 秒）
    if ZH_QUOTA > 0:
        zh_selected, zh_pool = _fetch_for_language(
            zh_issns, lookback_days, ZH_QUOTA, "zh", contact_email, pushed_set, ZH_QUERY,
            fallback_query=BROADER_ZH_QUERY,
        )
    else:
        logger.info("[zh] 配额为 0，跳过中文检索（OpenAlex 中文索引停在 2020）")
        zh_selected, zh_pool = [], []

    # 3. 中文不足时，用外文候选补齐（仍走历史过滤后的 pool）
    fill_count = 0
    current_total = len(en_selected) + len(zh_selected)
    if current_total < TOTAL_TARGET and en_pool:
        need = TOTAL_TARGET - current_total
        # 去掉已经在 en_selected / zh_selected 里的
        already = {history._title_fingerprint(p.get("title", "")) for p in en_selected + zh_selected}
        already.update({(p.get("doi") or "").lower().strip() for p in en_selected + zh_selected})
        fillers = [
            p for p in en_pool
            if (p.get("doi") or "").lower().strip() not in already
            and history._title_fingerprint(p.get("title", "")) not in already
        ]
        fillers = fillers[:need]
        fill_count = len(fillers)
        en_selected = _merge_unique(en_selected, fillers)
        logger.info(f"中文不足，补 {fill_count} 篇外文 → 外文共 {len(en_selected)}")

    top_papers = en_selected + zh_selected
    logger.info(
        f"最终筛选：外文 {len(en_selected)} + 中文 {len(zh_selected)} = {len(top_papers)}"
        f"（目标 {TOTAL_TARGET}，补位 {fill_count}）"
    )

    # 4. 候选池耗尽 → 经典高引回顾兜底，不再静默
    is_classic_mode = False
    if not top_papers and CLASSIC_FALLBACK > 0:
        classics = history.get_classic_picks(hist, CLASSIC_FALLBACK)
        if classics:
            top_papers = classics
            is_classic_mode = True
            logger.warning(
                f"候选池已耗尽，改用「经典高引回顾」推送 {len(classics)} 篇"
            )
        else:
            logger.warning("候选池耗尽，且历史为空无法生成回顾")

    if not top_papers:
        logger.warning("今日无可推送文献（中英都为空）")
        summary = {
            "date": datetime.now().isoformat(),
            "paper_count": 0,
            "en_count": 0,
            "zh_count": 0,
            "fill_count": 0,
            "status": "no_results",
        }
        _write_summary(summary)
        return summary

    # 4. 格式化
    html_body = render_html(top_papers, lookback_days=lookback_days)
    md_body = render_markdown(top_papers, lookback_days=lookback_days)

    archive_dir = Path("archive")
    archive_dir.mkdir(exist_ok=True)
    md_file = archive_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    md_file.write_text(md_body, encoding="utf-8")
    logger.info(f"Markdown 归档: {md_file}")

    # 5. 邮件推送
    today_str = datetime.now().strftime("%Y年%m月%d日")
    if is_classic_mode:
        subject = (
            f"[教育技术学·异步讨论] {today_str} · "
            f"经典回顾 {len(top_papers)} 篇（近期无新文献）"
        )
    elif zh_selected:
        subject = (
            f"[教育技术学·异步讨论] {today_str} · "
            f"外文 {len(en_selected)} + 中文 {len(zh_selected)}"
        )
    else:
        # 中文源暂不可用（OpenAlex CSSCI 索引停在 2020），不显示「中文 0」
        subject = (
            f"[教育技术学·异步讨论] {today_str} · "
            f"最新文献 {len(top_papers)} 篇"
        )
    sent = send_email(subject=subject, html_body=html_body, text_body=md_body)

    # 6. 更新历史（经典回顾不写入历史，避免占用候选池）
    if not is_classic_mode:
        new_hist = history.add_papers(hist, top_papers)
        history.save_history(new_hist)

    summary = {
        "date": datetime.now().isoformat(),
        "paper_count": len(top_papers),
        "en_count": len(en_selected),
        "zh_count": len(zh_selected),
        "fill_count": fill_count,
        "classic_mode": is_classic_mode,
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
