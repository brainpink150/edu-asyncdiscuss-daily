"""
Crossref 检索模块（兜底用）

当 OpenAlex 检索结果为空时，使用 Crossref REST API 作为兜底数据源。
Crossref 由 DOI 基金会运营，覆盖几乎所有正式出版的学术期刊。

文档：https://api.crossref.org/swagger-ui/index.html
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from .journals import journal_lookup

logger = logging.getLogger(__name__)

CROSSREF_BASE = "https://api.crossref.org/works"

CONTACT_EMAIL = "daily-bot@example.com"


def fetch_recent_papers_crossref(
    issns: List[str],
    lookback_days: int = 7,
    rows: int = 20,
    mailto: Optional[str] = None,
    query: str = "asynchronous discussion online discussion",
) -> List[Dict]:
    """用 Crossref 作为兜底检索。"""
    mailto = mailto or CONTACT_EMAIL

    today = datetime.now(timezone.utc).date()
    from_date = today - timedelta(days=lookback_days)

    # Crossref 用 filter=issn:xxx,yyy + query.bibliographic 做关键词检索
    params = {
        "filter": (
            f"issn:{','.join(issns)},"
            f"from-pub-date:{from_date.isoformat()},"
            "type:journal-article"
        ),
        "query.bibliographic": query,
        "sort": "published",
        "order": "desc",
        "rows": rows,
        "mailto": mailto,
    }

    url = f"{CROSSREF_BASE}?{urlencode(params)}"
    logger.info(f"Crossref 请求: {url[:200]}...")

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"Crossref 请求失败: {e}")
        return []

    return data.get("message", {}).get("items", [])


def normalize_crossref_item(item: Dict) -> Dict:
    """把 Crossref item 标准化为内部统一结构（与 openalex.normalize_work 对齐）。"""
    # 标题
    titles = item.get("title") or []
    title = (titles[0] if titles else "").strip()

    # 作者
    authors_list = item.get("author") or []
    names = []
    for a in authors_list[:5]:
        n = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if n:
            names.append(n)
    authors_display = ", ".join(names)
    if len(authors_list) > 5:
        authors_display += " et al."

    # 期刊信息：Crossref 返回 ISSN 列表
    issns = item.get("ISSN") or []
    venue_name = (item.get("container-title") or [""])[0]
    j_lookup = journal_lookup()
    journal_meta = {}
    for issn in issns:
        if issn in j_lookup:
            journal_meta = j_lookup[issn]
            break

    venue_abbr = journal_meta.get("abbr", venue_name)
    venue_full = journal_meta.get("name", venue_name)
    language = journal_meta.get("language", "en")

    # 发布日期：Crossref 用 date-parts 数组
    issued = item.get("issued", {}).get("date-parts", [[]])
    date_parts = issued[0] if issued and issued[0] else []
    if len(date_parts) >= 3:
        pub_date = f"{date_parts[0]:04d}-{date_parts[1]:02d}-{date_parts[2]:02d}"
    elif len(date_parts) >= 2:
        pub_date = f"{date_parts[0]:04d}-{date_parts[1]:02d}"
    else:
        pub_date = ""

    # 摘要（Crossref 可能含 JATS XML 标签，需要去掉）
    abstract_raw = item.get("abstract") or ""
    import re
    abstract = re.sub(r"<[^>]+>", "", abstract_raw).strip()

    # URL
    doi = item.get("DOI", "")
    doi_url = f"https://doi.org/{doi}" if doi else item.get("URL", "")

    # 主题（Subject）
    subjects = item.get("subject") or []

    return {
        "paper_id": item.get("URL", ""),
        "doi": doi,
        "title": title,
        "authors": authors_display,
        "venue": venue_abbr,
        "venue_full": venue_full,
        "date": pub_date,
        "abstract": abstract,
        "url": doi_url,
        "cited_by_count": item.get("is-referenced-by-count", 0),
        "keywords": subjects[:5],
        "language": language,
    }