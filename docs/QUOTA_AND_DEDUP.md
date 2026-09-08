# 配额 + 去重改造说明

## 改了什么

| 文件 | 改动 | 解决的问题 |
|------|------|------------|
| `src/history.py` | **新增** 推送历史管理 | 跨日重复 |
| `main.py` | **重写** 中英分路抓取 + 配额 + 历史过滤 | 数量不稳 / 中英比例失配 |
| `.github/workflows/daily-papers.yml` | **重写** 加 GITHUB_TOKEN 写权限 + 自动 commit 历史 | 历史无法跨运行持久化 |
| `src/fetchers/crossref.py` | **重写** 防 400 崩溃 + ISSN 分批请求 | 中文 Crossref 兜底失败 |
| `docs/QUOTA_AND_DEDUP.md` | **新增** 本文档 | — |

## 三个问题对应的修复

### 1. 「4 篇而不是 5 篇」

**根因**：`lookback_days=7` 太短，OpenAlex 对中文期刊覆盖本来就有缺口，7 天里中文候选就 0-1 篇。

**修复**：
- 窗口从 7 天 → **60 天**（候选池扩大到 8 倍）
- 中英文分路抓取，**外文 3 篇** + **中文 2 篇** 各自独立配配额
- 每路候选拉到 `quota × 8` 篇，避免被历史过滤后断流

### 2. 「每日重复很多」

**根因**：原来完全没有"哪些 ID 已经推过"的记忆。OpenAlex 索引常常延迟，一篇论文实际发布 30 天前、OpenAlex 这周才同步进来，所以"上周推过的"这周又冒出来。

**修复**：
- 新增 `data/pushed_history.json`，记录已推过的 **DOI** + **标题指纹**（DOI 缺失时 fallback）
- 抓取后排序前先 `history.is_pushed()` 过滤
- 推送成功后立即把新 ID 写入历史
- GitHub Actions 跑完会用 `GITHUB_TOKEN` 把这份历史 **自动 commit 回仓库**
- 下次 checkout 时自动带上完整历史

**指纹算法**（`src/history.py`）：
```python
def _title_fingerprint(title):
    norm = "".join(ch.lower() for ch in title if ch.isalnum())
    return sha1(norm[:60]).hexdigest()
```
中文 / 英文 / 标点差异都能统一成同一指纹。

### 3. 「每日外文 3 / 中文 2」

**根因**：之前是合并排序取 top5，运气不好就 4 英 1 中。

**修复**：
- `main.py` 拆出 `_fetch_for_language()`，每种语言独立走抓取 → 过滤 → 排序 → 截取
- 配置项（环境变量 + Actions input）：
  - `EN_QUOTA=3`
  - `ZH_QUOTA=2`
  - `LOOKBACK_DAYS=60`

### 4. 「中文源返回 0，Crossref 兜底报 400」

**根因**：
- OpenAlex 对国内 CSSCI 期刊收录极少
- Crossref 批量请求里只要有一个坏 ISSN 或 type 标签不匹配，就整批 400
- 之前 Crossref 一直用英文关键词搜中文期刊，相关性也差

**修复**：
- `crossref.py` 批量请求失败后，自动降级为**逐个 ISSN 请求**，隔离坏 ISSN
- 中文期刊请求时去掉 `type:journal-article` 限制（中文期刊在 Crossref 里的 type 标签不一致）
- `main.py` 中文路径改用中文关键词：`异步讨论|在线讨论|网络讨论|...`
- `main.py` 中文若仍不足，启用**更宽关键词 + 2 倍窗口兜底**：
  - 关键词扩展为：在线学习 / 网络学习 / 远程教育 / 开放教育 / 教育技术 / 信息化教学 / 混合式教学 / 慕课 / MOOC / 学习分析 / 异步交互 / 在线交互
- 兜底后仍不足 2 篇时，**用高相关外文候选补齐到 5 篇**，日志会写明"中文不足，补 X 篇外文"



```bash
cd ~/Projects/edu-asyncdiscuss-daily

# 1. 看一眼 diff，确认改动
git status
git diff --stat

# 2. 提交
git add src/history.py main.py .github/workflows/daily-papers.yml
git commit -m "feat: 中英 3:2 配额 + 推送历史去重"

# 3. 推送（如果 git push 失败，换手机热点再试）
git push origin main
```

## 手动验证

推到 GitHub 后，去 Actions 页面手动触发 `workflow_dispatch`，**重点看**：
1. 日志里有没有 `[en] 标准化 X → 历史过滤后 Y`（说明历史过滤生效）
2. summary.json 里 `en_count` 和 `zh_count` 是不是 3 + 2
3. 推送后仓库根目录多一个 `data/pushed_history.json`
4. Actions 日志最后一步有 `chore: 更新推送历史 (...)` 的 commit 记录

## 进阶方案（中文覆盖差怎么破）

OpenAlex 对中文 CSSCI 期刊的覆盖确实烂（很多《电化教育研究》《中国远程教育》的文章没有 DOI 或未被索引）。如果跑了一周发现中文 2 篇总凑不齐，可考虑：

1. **接万方开放 API**（需申请开发者账号，免费）：覆盖度比 OpenAlex 好
2. **接豆瓣读书 / 国家社科文献中心**：作为补充源
3. **降级方案**：当中文不足 2 篇时，邮件里写明"今日中文文献 0-1 篇"，避免空缺

这部分我留着不动，等你先跑一周看实际数据再决定要不要升级。

## 历史清理

如果某天想重置历史（比如想重新看一遍所有近期论文）：

```bash
# 本地
rm data/pushed_history.json
git add -A && git commit -m "chore: 重置推送历史" && git push
```

## 已知限制

- GitHub Actions 默认的 `GITHUB_TOKEN` 是仓库级 token，commit 历史会显示 `daily-papers-bot` 用户名（不是你自己）。如想用自己账号名，把 commit 那两步换成 `gh auth setup-git && gh repo sync` 或配置 deploy key。
- 如果连续几天没跑（cron 失败 / 仓库停用），历史会停在那一天。下次恢复后从断点继续，不会一次性重发之前所有的。
