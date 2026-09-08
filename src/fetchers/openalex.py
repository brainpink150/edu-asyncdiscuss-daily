"""
OpenAlex 检索模块

OpenAlex (https://openalex.org) 是一个开放的学术文献索引，
覆盖 Crossref 全量元数据，更新速度接近 Web of Science。
无需 API Key，通过 mailto 标识可获得更高的速率限制。

文档：https://docs.openalex.org/
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from .journals import journal_lookup

logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org/works"

# 与"在线异步讨论"主题相关的核心检索词
# 同时覆盖中文/英文常见表达，OpenAlex 会按 title + abstract 做相关性排序
KEYWORDS = [
    "asynchronous discussion",
    "online discussion",
    "online asynchronous discussion",
    "asynchronous online discussion",
    "discussion forum",
    "computer-mediated discussion",
    "online forum",
    "异步讨论",
    "在线讨论",
    "异步交互",
    "在线交互",
    "网络讨论",
]

# 备用联系邮箱（建议换成你自己的，提高 OpenAlex 速率限制）
CONTACT_EMAIL = "daily-bot@example.com"


def build_search_query() -> str:
    """构造 OpenAlex 的 search 查询：用 OR 串接所有关键词。"""
    return "|".join(KEYWORDS)


def fetch_recent_papers(
    issns: List[str],
    lookback_days: int = 7,
    per_page: int = 25,
    mailto: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict]:
    """
    在指定期刊集合中，检索最近 lookback_days 天内、
    标题或摘要含指定关键词的文献。

    Args:
        query: 覆盖默认 KEYWORDS 的自定义查询；默认用 OpenAlex OR 语法 "a|b|c"。

    返回 OpenAlex work 的原始 JSON 列表。
    """
    mailto = mailto or CONTACT_EMAIL
    search_query = query or build_search_query()

    # 计算日期窗口（OpenAlex 用 from_publication_date 过滤）
    today = datetime.now(timezone.utc).date()
    from_date = today - timedelta(days=lookback_days)

    # ISSN 多选用 | 分隔（OpenAlex 标准语法）
    issn_filter = "|".join(issns)

    params = {
        "filter": (
            f"primary_location.source.issn:{issn_filter},"
            f"from_publication_date:{from_date.isoformat()},"
            "type:article|review"
        ),
        "search": search_query,
        "sort": "publication_date:desc",
        "per_page": per_page,
        "mailto": mailto,
    }

    url = f"{OPENALEX_BASE}?{urlencode(params)}"
    logger.info(f"OpenAlex 请求: {url[:200]}...")

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"OpenAlex 请求失败: {e}")
        return []

    results = data.get("results", [])
    logger.info(f"OpenAlex 返回 {len(results)} 条原始结果")
    return results


def normalize_work(work: Dict) -> Dict:
    """
    把 OpenAlex work 标准化成我们内部统一的字段结构。

    输出字段：
        - paper_id: OpenAlex ID
        - doi: DOI 字符串（可能为空）
        - title: 标题
        - authors: 作者列表（最多 5 人 + et al.）
        - venue: 期刊缩写
        - venue_full: 期刊全名
        - date: 发布日期（YYYY-MM-DD）
        - abstract: 摘要（OpenAlex 有时只提供 inverted index，需要还原）
        - url: 原文链接（DOI 优先）
        - cited_by_count: 被引数
        - keywords: 概念 / 关键词
        - language: 期刊语言
    """
    # 标题：OpenAlex 新版 title 是字符串（旧版 / 部分接口可能返回数组），统一兼容
    raw_title = work.get("title") or work.get("display_name") or ""
    if isinstance(raw_title, list):
        title = (raw_title[0] if raw_title else "").strip()
    else:
        title = str(raw_title).strip()

    # 作者
    authorships = work.get("authorships") or []
    author_names = []
    for a in authorships[:5]:
        name = (a.get("author") or {}).get("display_name")
        if name:
            author_names.append(name)
    if len(authorships) > 5:
        authors_display = ", ".join(author_names) + " et al."
    else:
        authors_display = ", ".join(author_names)

    # 期刊信息
    primary_loc = work.get("primary_location") or {}
    source = primary_loc.get("source") or {}
    issn_l = source.get("issn_l") or ""
    venue_name = source.get("display_name") or ""

    j_lookup = journal_lookup()
    journal_meta = j_lookup.get(issn_l, {})
    venue_abbr = journal_meta.get("abbr", venue_name)
    venue_full = journal_meta.get("name", venue_name)
    language = journal_meta.get("language", "en")

    # 发布日期
    pub_date = work.get("publication_date") or ""

    # 摘要：OpenAlex 用 inverted index 存，需要还原成文本
    abstract_inverted = work.get("abstract_inverted_index") or {}
    abstract = _reconstruct_abstract(abstract_inverted)

    # 原文链接：DOI 优先
    doi = work.get("doi") or ""
    if doi and doi.startswith("https://doi.org/"):
        doi_url = doi
    elif doi:
        doi_url = f"https://doi.org/{doi}"
    else:
        doi_url = primary_loc.get("landing_page_url") or work.get("id") or ""

    # 概念 / 关键词
    concepts = work.get("concepts") or []
    keywords = [c.get("display_name") for c in concepts[:5] if c.get("display_name")]

    return {
        "paper_id": work.get("id", ""),
        "doi": doi.replace("https://doi.org/", "") if doi else "",
        "title": title,
        "authors": authors_display,
        "venue": venue_abbr,
        "venue_full": venue_full,
        "date": pub_date,
        "abstract": abstract,
        "url": doi_url,
        "cited_by_count": work.get("cited_by_count", 0),
        "keywords": keywords,
        "language": language,
    }


def _reconstruct_abstract(inverted_index: Dict) -> str:
    """
    OpenAlex 摘要格式：{word: [positions]}
    反向还原成可读文本。
    """
    if not inverted_index:
        return ""
    # 找出最大位置，确定数组长度
    max_pos = 0
    for positions in inverted_index.values():
        if positions:
            max_pos = max(max_pos, max(positions))
    words = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            if pos < len(words):
                words[pos] = word
    return " ".join(words).strip()


def deduplicate(papers: List[Dict]) -> List[Dict]:
    """按 DOI 去重。"""
    seen = set()
    unique = []
    for p in papers:
        key = p.get("doi") or p.get("paper_id")
        if key and key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def rank_papers(papers: List[Dict], top_k: int = 5) -> List[Dict]:
    """
    对候选文献排序：
    1. 优先近期
    2. 摘要与关键词命中数加权
    """
    keyword_set = set(k.lower() for k in KEYWORDS)

    def score(p: Dict) -> float:
        s = 0.0
        # 摘要命中关键词次数
        abstract = (p.get("abstract") or "").lower()
        title = (p.get("title") or "").lower()
        for kw in keyword_set:
            if kw in abstract:
                s += 2.0
            if kw in title:
                s += 3.0
        # 被引数加分（对数缩放，避免老论文霸榜）
        s += min(2.0, (p.get("cited_by_count") or 0) ** 0.5 * 0.3)
        # 时效性加分（越新越高）
        date = p.get("date") or ""
        if date:
            try:
                d = datetime.fromisoformat(date)
                days_ago = (datetime.now(timezone.utc) - d.replace(tzinfo=timezone.utc)).days
                s += max(0.0, (30 - days_ago) * 0.1)
            except ValueError:
                pass
        return s

    papers_sorted = sorted(papers, key=score, reverse=True)
    return papers_sorted[:top_k]