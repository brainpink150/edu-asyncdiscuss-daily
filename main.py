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
import time
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

# ============================================================================
# 主题分组（2026-09-29 扩充）
#
# 背景 1：2026-09-16 实测，原「异步讨论」窄主题在 10 本顶刊 60 天窗口只有 27 条
#         候选，每天 5 篇 6 天推完断流。故窗口放宽到 365 天、主题放宽到教育技术学大类。
#
# 背景 2：2026-09-28 实测，**OpenAlex 的 search 参数里 OR 关键词超过约 20 个会
#         超时**（32 词查询 34 秒后失败）。所以不能把所有关键词拼成一个大 query，
#         改为分组检索 + 本地合并。每组词数控制在 10 个以内。
#
# 每日策略：7 个组里按日期轮换选 5 组、每组取 1 篇，保证每天推送覆盖不同方向，
#           7 天一个完整周期（每组 5 次）。
#
# 各组命中量为 2026-09-28 实测（365 天窗口 / 10 本教育技术顶刊）。
# ============================================================================
TOPIC_GROUPS = [
    {
        "key": "core",
        "label": "教育技术核心",
        "hits": 456,
        "keywords": [
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
        ],
    },
    {
        "key": "ai",
        "label": "AI 教育应用",
        "hits": 299,
        "keywords": [
            "generative AI education",
            "AI literacy",
            "intelligent tutoring system",
            "conversational agent",
            "ChatGPT education",
            "large language model education",
            "human-AI collaboration",
            "AI agent",
        ],
    },
    {
        "key": "teacher",
        "label": "教师·师范教育",
        "hits": 307,
        "keywords": [
            "teacher education",
            "pre-service teacher",
            "preservice teacher",
            "teacher professional development",
            "TPACK",
            "teacher competence",
            "teacher training",
        ],
    },
    {
        "key": "collab",
        "label": "协作与认知",
        "hits": 327,
        "keywords": [
            "collaborative learning",
            "knowledge building",
            "argumentation",
            "social presence",
            "cognitive presence",
            "community of inquiry",
            "peer feedback",
        ],
    },
    {
        "key": "method",
        "label": "学习科学教法",
        "hits": 334,
        "keywords": [
            "metacognition",
            "formative assessment",
            "gamification",
            "problem-based learning",
            "project-based learning",
            "inquiry-based learning",
            "scaffolding",
        ],
    },
    {
        "key": "tech",
        "label": "技术学习形态",
        "hits": 341,
        "keywords": [
            "mobile learning",
            "virtual reality",
            "augmented reality",
            "adaptive learning",
            "personalized learning",
            "microlearning",
            "immersive learning",
        ],
    },
    {
        "key": "affect",
        "label": "动机与情感",
        "hits": 493,
        "keywords": [
            "motivation",
            "engagement",
            "self-efficacy",
            "learning anxiety",
            "academic emotion",
            "student satisfaction",
        ],
    },
]

# 向后兼容：旧代码里引用 EN_QUERY 的地方（Crossref 兜底等）用核心组关键词
EN_QUERY = "|".join(TOPIC_GROUPS[0]["keywords"])

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

# 主题组之间的请求间隔（秒）。
# 2026-09-29 实测：GitHub Actions 的共享 IP 上 OpenAlex 限流很严，
# 第 1 组拿到数据后第 2 组起连续 429（2 秒间隔不够），提到 8 秒后改善。
GROUP_INTERVAL = int(os.getenv("GROUP_INTERVAL", "8"))


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
    rank_keywords: list = None,
    per_page: int = None,
    max_pages: int = None,
) -> tuple[list, list]:
    """
    单次抓取尝试：OpenAlex → Crossref → 标准化 → 历史过滤 → 排序。

    返回 (selected, pool)：
    - selected: 已截取的 top 配额
    - pool: 完整候选池（用于后续补位）
    """
    # per_page：单页条数，默认拉到 OpenAlex 上限 200。
    # 之前 30 太小：按日期倒序取回的最新 30 条大多是已推过的，
    # 历史过滤后只剩 13 篇，仍会很快断流。
    per_page = per_page or int(os.getenv("PER_PAGE", "200"))

    raw = openalex.fetch_recent_papers(
        issns=issns,
        lookback_days=lookback_days,
        per_page=per_page,
        mailto=contact_email,
        query=query,
        max_pages=max_pages or 5,
    )
    source = "openalex"

    if not raw:
        logger.warning(f"[{language}] OpenAlex 无结果，尝试 Crossref 兜底")
        raw = crossref.fetch_recent_papers_crossref(
            issns=issns,
            lookback_days=lookback_days,
            rows=max(quota * 8, 30),
            mailto=contact_email,
            query=_to_crossref_query(query),
        )
        source = "crossref"

    if not raw:
        logger.warning(f"[{language}] 本次尝试所有数据源均无结果")
        return [], []

    # 2026-09-29 修复：以前无论数据来自哪个源，都用 openalex.normalize_work 处理。
    # 但 Crossref 的字段是 DOI（大写）且没有 id 字段，normalize 后 doi/paper_id
    # 全为空，deduplicate() 用 doi or paper_id 做 key 时整批被丢弃 —— 实测
    # 「Crossref 返回 40 条 → 标准化 0」，兜底形同虚设。
    # 这里按来源分派：Crossref 数据走 crossref.normalize_crossref_item。
    normalizer = (
        crossref.normalize_crossref_item if source == "crossref"
        else openalex.normalize_work
    )
    papers = [normalizer(w) for w in raw]
    papers = openalex.deduplicate(papers)

    before = len(papers)
    papers = [p for p in papers if not history.is_pushed(p, pushed_set)]
    logger.info(f"[{language}] 标准化 {before} → 历史过滤后 {len(papers)}")

    if not papers:
        return [], []

    ranked = openalex.rank_papers(
        papers, top_k=max(quota, len(papers)), keywords=rank_keywords
    )
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
    rank_keywords: list = None,
    per_page: int = None,
    max_pages: int = None,
) -> tuple[list, list]:
    """
    带兜底策略的单语种抓取。

    1. 先用精准关键词 + lookback_days 抓取
    2. 如果不够配额，用 fallback_query + 2 倍窗口再试
    返回 (selected, pool)
    """
    selected, pool = _try_fetch(
        issns, lookback_days, quota, language, contact_email, pushed_set, query,
        rank_keywords=rank_keywords, per_page=per_page, max_pages=max_pages,
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
            rank_keywords=rank_keywords,
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
    # 必须是真实邮箱：OpenAlex 只给真实邮箱 polite pool 配额。
    # 2026-09-29 前用 daily-bot@example.com（假邮箱），导致连续三天 429。
    contact_email = os.getenv("CONTACT_EMAIL") or "1985403252@qq.com"

    # 1. 加载历史
    hist = history.load_history()
    pushed_set = history.get_pushed_set(hist)
    logger.info(f"历史已记录 {len(pushed_set)} 条论文标识")

    # 2. 按主题分组轮换抓取（每组 1 篇，保证每天覆盖不同方向）
    en_issns = [j["issn"] for j in INTERNATIONAL_JOURNALS]
    zh_issns = [j["issn"] for j in DOMESTIC_JOURNALS]

    # 7 个组按日期轮换取 5 组：7 天一个完整周期，每组每周期出现 5 次
    day_index = datetime.now().toordinal()
    start = day_index % len(TOPIC_GROUPS)
    today_groups = [
        TOPIC_GROUPS[(start + i) % len(TOPIC_GROUPS)] for i in range(TOTAL_TARGET)
    ]
    logger.info(
        f"今日主题轮换（第 {day_index} 天，起点 {start}）: "
        + " › ".join(g["label"] for g in today_groups)
    )

    en_selected: list = []
    en_pool: list = []
    for g in today_groups:
        sel, pool = _fetch_for_language(
            en_issns,
            lookback_days,
            1,  # 每组取 1 篇
            "en",
            contact_email,
            pushed_set,
            "|".join(g["keywords"]),
            rank_keywords=g["keywords"],
            # 每组只要 1 篇，不必拉满：单页 100 条、只取 1 页。
            # 实测 5 组 × 5 页 = 25 个请求会打爆 OpenAlex 限流（429），
            # 降到 5 组 × 1 页 = 5 个请求后与改造前持平。
            per_page=100,
            max_pages=1,
        )
        if sel:
            en_selected = _merge_unique(en_selected, sel[:1])
        en_pool = _merge_unique(en_pool, pool)
        # 组间留间隔，避免短时间密集请求被 OpenAlex 限流。
        # 实测：GitHub Actions 的 IP 上，第 1 组成功、第 2 组起连续 429
        # （2 秒间隔不够），8 秒间隔后命中率明显改善。
        time.sleep(GROUP_INTERVAL)

    logger.info(
        f"主题轮换抓取完成：{len(en_selected)} / {TOTAL_TARGET} 篇"
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

    # 3. 某主题组没取到时，用其他组的候选补齐（仍走历史过滤后的 pool）
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
        logger.info(
            f"部分主题组无新文献，从候选池补 {fill_count} 篇 → 共 {len(en_selected)}"
        )

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
