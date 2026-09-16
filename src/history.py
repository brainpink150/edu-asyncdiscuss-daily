"""
推送历史管理 —— 解决"每日重复"问题

持久化已推送的论文标识（DOI + 标题指纹），作为去重第二层。
- 文件位置: data/pushed_history.json
- 格式: {"dois": [...], "title_hashes": [...], "last_updated": "..."}
- GitHub Actions 通过 GITHUB_TOKEN 自动 commit 回仓库，下一次运行自动带历史
"""

import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Set

logger = logging.getLogger(__name__)

HISTORY_PATH = Path("data/pushed_history.json")

# 历史保留上限：超出后裁掉最早的（按 title_hash 字典序，简单实现）
MAX_HISTORY_SIZE = 800


def _title_fingerprint(title: str) -> str:
    """
    标题指纹：DOI 缺失时用标题做 fallback 去重键。
    - 统一小写
    - 去除所有非字母数字字符（包含中文标点）
    - 取前 60 字符做 SHA1
    """
    if not title:
        return ""
    norm = "".join(ch.lower() for ch in title if ch.isalnum())
    return hashlib.sha1(norm[:60].encode("utf-8")).hexdigest()


def load_history() -> Dict:
    """加载历史；不存在则返回空结构。"""
    if not HISTORY_PATH.exists():
        return {"dois": [], "title_hashes": [], "last_updated": ""}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"历史文件损坏，重置为空: {e}")
        return {"dois": [], "title_hashes": [], "last_updated": ""}


def get_pushed_set(history: Dict) -> Set[str]:
    """合并 DOI + 标题指纹到一个集合，方便快速判断。"""
    return set(history.get("dois", [])) | set(history.get("title_hashes", []))


def is_pushed(paper: Dict, pushed_set: Set[str]) -> bool:
    """单条论文是否已推过。"""
    doi = (paper.get("doi") or "").lower().strip()
    if doi and doi in pushed_set:
        return True
    fp = _title_fingerprint(paper.get("title", ""))
    if fp and fp in pushed_set:
        return True
    return False


def add_papers(history: Dict, papers: List[Dict]) -> Dict:
    """
    把刚推送的论文合入历史。

    除 DOI / 标题指纹外，额外保存论文摘要信息（papers 字段），
    用于候选池耗尽时的「经典高引回顾」。
    """
    dois = set(history.get("dois", []))
    hashes = set(history.get("title_hashes", []))
    archived = {p.get("_fp"): p for p in history.get("papers", []) if p.get("_fp")}

    for p in papers:
        doi = (p.get("doi") or "").lower().strip()
        if doi:
            dois.add(doi)
        fp = _title_fingerprint(p.get("title", ""))
        if fp:
            hashes.add(fp)
            archived[fp] = {
                "_fp": fp,
                "title": p.get("title", ""),
                "doi": p.get("doi", ""),
                "url": p.get("url", ""),
                "authors": p.get("authors", ""),
                "venue": p.get("venue", ""),
                "date": p.get("date", ""),
                "cited_by_count": p.get("cited_by_count", 0),
                "abstract": (p.get("abstract") or "")[:400],
            }

    papers_list = list(archived.values())
    if len(dois) + len(hashes) > MAX_HISTORY_SIZE:
        logger.warning(
            f"历史已超 {MAX_HISTORY_SIZE} 条，建议清空或调大上限。"
            f"当前 dois={len(dois)}, hashes={len(hashes)}"
        )

    return {
        "dois": sorted(dois),
        "title_hashes": sorted(hashes),
        "papers": papers_list,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def get_classic_picks(history: Dict, top_k: int) -> List[Dict]:
    """
    候选池耗尽时的兜底：从已推送历史里挑被引最高的几篇，做「经典回顾」。

    会打上 is_classic=True + abstract 前缀标记，供邮件模板区分。
    """
    papers = history.get("papers") or []
    if not papers:
        return []

    scored = sorted(
        papers,
        key=lambda p: (p.get("cited_by_count") or 0, p.get("date") or ""),
        reverse=True,
    )

    picks = []
    for p in scored[:top_k]:
        item = dict(p)
        item["is_classic"] = True
        item["abstract"] = "【经典回顾】" + (p.get("abstract") or "")
        picks.append(item)
    return picks


def save_history(history: Dict) -> None:
    """写入历史文件。Actions 里这步后会由 GITHUB_TOKEN 自动 commit。"""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        f"历史已更新: {len(history['dois'])} DOIs + "
        f"{len(history['title_hashes'])} 标题指纹"
    )
