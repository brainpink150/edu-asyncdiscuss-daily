# 配额 + 去重改造说明

> 最后更新：2026-09-29（第三版：主题分组轮换 + 修复 429 限流与 Crossref 死代码）

---

## 零、2026-09-29 第三次事故与修复

### 现象
9-27 / 9-28 / 9-29 连续三天，Actions 全绿、邮件照发，但推的是「经典高引回顾」旧文，没有新文献。

### 根因一：OpenAlex 429 限流，且代码遇到 429 直接放弃
```
[ERROR] OpenAlex 请求失败（第 1 页）: 429 Client Error: Too Many Requests
[INFO]  OpenAlex 返回 0 条原始结果
[WARNING] 候选池已耗尽，改用「经典高引回顾」推送 3 篇
```
两层问题：
1. `mailto` 用的是假邮箱 `daily-bot@example.com`。OpenAlex 只给**真实邮箱**进 polite pool。
2. 代码遇到 429 直接 `break`，不重试 —— 一次限流就整次运行报废。

### 根因二：Crossref 兜底是死代码（一直没生效过）
`_try_fetch` 里无论数据来自 OpenAlex 还是 Crossref，都用 `openalex.normalize_work()` 处理。
但 Crossref 的字段是 `DOI`（**大写**）且**没有 `id` 字段**，normalize 后 `doi` / `paper_id` 全空，
`deduplicate()` 用 `doi or paper_id` 做 key 时整批被丢弃。

日志实证：`Crossref 最终返回 40 条` → `[en] 标准化 0`。

### 根因三：主题分组后请求数暴涨，反而加剧限流
改成 5 组轮换后是 `5 组 × 5 页分页 = 25 个请求`，比原来的 5 个翻了 5 倍。

### 修复
| 改动 | 文件 |
|------|------|
| 默认 `mailto` 换真实邮箱（可用 `CONTACT_EMAIL` secret 覆盖） | `main.py` / `openalex.py` / `crossref.py` |
| 429 指数退避重试（5s / 10s / 15s，每页最多 3 次） | `openalex.py` |
| 按来源分派标准化函数：Crossref 数据走 `normalize_crossref_item` | `main.py` |
| 每组拉取量降到 `per_page=100, max_pages=1`（5 组 = 5 个请求） | `main.py` |
| 组间 `time.sleep(2)` | `main.py` |

**修复后实测**：429 触发后退避重试成功取到数据；某组重试耗尽时 Crossref 兜底真正顶上（`标准化 30 → 过滤后 17`）。

---

## 零之二、主题分组轮换（2026-09-29 扩充）

### 为什么分组而不是拼成一个大 query
**实测：OpenAlex 的 `search` 参数里 OR 关键词超过约 20 个会超时**（32 词查询 34 秒后失败，25 词也失败）。
所以把关键词拆成 7 个组，每组 ≤10 词，分别请求后本地合并。

### 每日策略
7 个组按日期轮换取 5 组、**每组 1 篇**：7 天一个完整周期，每组每周期出现 5 次。
好处是不会连着几天全是同一主题。

### 各组命中量（2026-09-28 实测：365 天窗口 / 10 本教育技术顶刊）

| 组 | 词数 | 命中 | 抽样标题（真实） |
|----|------|------|------------------|
| 教育技术核心 | 10 | 456 | multimodal learning analytics |
| AI 教育应用 | 8 | 299 | LLM-based Socratic conversational… |
| 教师·师范教育 | 7 | 307 | Co-constructing adaptive lesson plans with GenAI: Pre-service… |
| 协作与认知 | 7 | 327 | Students' interaction patterns of online dialogic peer feedback |
| 学习科学教法 | 7 | 334 | metacognitive scaffolding-supported online… |
| 技术学习形态 | 7 | 341 | student-AI interaction dynamics in multi-agent… |
| 动机与情感 | 6 | 493 | Chinese EFL… / Mathematics Achievement… |

> ⚠️ 「动机与情感」组泛词较多，抽样已出现与教育技术弱相关的文献（EFL、数学成就）。
> 若觉得推送质量被稀释，把该组从 `TOPIC_GROUPS` 里删掉即可。

> ⚠️ A+B+C 合并去重后的总数**未实测**（实测时自身触发 429）。粗估 800-1200，这是估算值。

---

## 一、当前生效配置（2026-09-16 起）

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LOOKBACK_DAYS` | `365` | 回溯窗口。365 天 + 宽关键词实测 445 条候选 |
| `EN_QUOTA` | `5` | 外文篇数 |
| `ZH_QUOTA` | `0` | 中文篇数。**默认关闭，见第三节实测结论** |
| `CLASSIC_FALLBACK` | `3` | 候选池耗尽时，改推几篇「经典高引回顾」（0 = 关闭，静默不发） |
| `PER_PAGE` | `200` | OpenAlex 单页条数（硬上限 200），配合 cursor 分页最多拉 5 页 |

推送节奏：**每天 5 篇，实测候选池 415 篇 → 可连续推 83 天**。

---

## 二、断流事故复盘（2026-09-15 / 09-16 两天没收到邮件）

### 现象
Actions 每天照常运行、状态全绿 ✓，但收不到邮件。

### 根因：不是程序坏了，是**候选池被推光了**

```
历史已记录 60 条论文标识
OpenAlex 返回 29 条原始结果
[en] 标准化 29 → 历史过滤后 0        ← 29 条全部已推过
最终筛选：外文 0 + 中文 0 = 0
今日无可推送文献（中英都为空）        ← 当时的静默逻辑，不发信
```

从 09-08 改造后开始推：每天 5 篇 × 6 天 = 30 篇，**正好把 27-30 条的池子推完**。

### 三重原因叠加

| 层 | 问题 | 数据 |
|----|------|------|
| 窗口太短 | `LOOKBACK_DAYS=60` | 候选仅 **27 条** → 撑 6 天 |
| 关键词太窄 | 只搜 asynchronous / online discussion | 命中面过窄 |
| 单页截断 | `per_page=30` | OpenAlex 明明有 445 条，只取了最新 30 条，且大多已推过 |

### 修复

1. **窗口 60 → 365 天**，关键词放宽到教育技术学大类
   （online learning / blended learning / learning analytics / educational technology / MOOC 等）
2. **`per_page` → 200**（OpenAlex 单页上限）
3. **新增 cursor 分页**（`src/fetchers/openalex.py`）：自动翻页把候选池拉满，最多 5 页 / 1000 条

### 效果实测

| 配置 | 候选池 | 按每天 5 篇能撑 |
|------|--------|------------------|
| 修复前（窄关键词 + 60 天 + 单页 30） | 27 条 | **6 天** |
| 放宽关键词 + 365 天 + 单页 200 | 170 条 | 34 天 |
| **放宽关键词 + 365 天 + cursor 分页（当前）** | **415 条** | **83 天** |

排序仍按「关键词命中 + 被引 + 时效性」加权，放开窗口不会让主题跑偏——实测 top1 仍是异步讨论主题的顶刊文献。

---

## 三、中文源：为什么默认关掉了（重要）

2026-09-16 实测了三条路，结论是**免费源下做不到「每天 2 篇权威中文文献」**：

| 方案 | 实测结果 |
|------|----------|
| CSSCI 核心刊（电化教育研究 / 中国远程教育 / 开放教育研究 / 现代教育技术 / 远程教育杂志 / 中国电化教育）用 source ID 检索 | **最新文献停在 2020 年**。这些刊在 OpenAlex 有收录（数百至 1800 篇），但索引严重滞后，近 5 年无数据 |
| 用 CSSCI 的 ISSN 过滤 | 命中 2668 条，但首条是英文——这些刊的 `issn_l` 多为 `None`，ISSN 匹配偏了 |
| 不限期刊 + 中文关键词 + `language:zh` | 近一年 1440 条，但来源全是水刊（《教育決策與分析》《学知 Xue Zhi》《国际临床与研究》…），被引 0-5 |

**处理**：`ZH_QUOTA` 默认 `0`，中文那一路直接跳过（省掉一次必定 400 的 Crossref 请求，约 30 秒）。
代码结构完整保留，**日后接万方 / CNKI 开放 API 后，把 `ZH_QUOTA` 设回 `2`、`EN_QUOTA` 设回 `3` 即可恢复 3:2**。

> 邮件主题在纯外文模式下显示「最新文献 5 篇」，不会出现难看的「中文 0」。

---

## 四、去重机制

### 根因
原来完全没有"哪些 ID 已经推过"的记忆。OpenAlex 索引常延迟（论文实际发布 30 天前、这周才同步进来），所以"上周推过的"这周又冒出来。

### 修复
- 新增 `data/pushed_history.json`，记录已推过的 **DOI** + **标题指纹**（DOI 缺失时 fallback）
- 抓取后排序前先 `history.is_pushed()` 过滤
- 推送成功后立即把新 ID 写入历史
- GitHub Actions 跑完用 `GITHUB_TOKEN` 把历史**自动 commit 回仓库**
- 下次 checkout 自动带上完整历史

**指纹算法**（`src/history.py`）：
```python
def _title_fingerprint(title):
    norm = "".join(ch.lower() for ch in title if ch.isalnum())
    return sha1(norm[:60]).hexdigest()
```
中文 / 英文 / 标点差异都能统一成同一指纹。

### 经典回顾兜底

候选池彻底耗尽时不再静默，而是从**已推送历史里挑被引最高**的几篇，标注「【经典回顾】」重新推送：

```python
CLASSIC_FALLBACK = int(os.getenv("CLASSIC_FALLBACK", "3"))
```

历史文件从 2026-09-16 起会保存论文详情（标题 / 作者 / 摘要 / 被引数），
所以**经典回顾要等新版跑几天、攒够详情后才会有内容**。

---

## 五、历史文件

| 文件 | 改动 | 解决的问题 |
|------|------|------------|
| `src/history.py` | 推送历史 + 详情留存 + 经典回顾 | 跨日重复 / 池空静默 |
| `main.py` | 中英分路抓取 + 配额 + 历史过滤 + 经典兜底 | 数量不稳 / 中英比例失配 / 断流 |
| `src/fetchers/openalex.py` | cursor 分页 + 宽关键词 | 候选池过小导致 6 天推完 |
| `src/fetchers/crossref.py` | 防 400 崩溃 + ISSN 分批 | 中文 Crossref 兜底失败 |
| `.github/workflows/daily-papers.yml` | 写权限 + 自动 commit 历史 + 新默认参数 | 历史无法持久化 |

---

## 六、手动验证

推到 GitHub 后，去 Actions 页面手动触发 `workflow_dispatch`，**重点看**：

1. `[en] 标准化 445 → 历史过滤后 410`（第二个数字应为总数减已推数）
2. `最终筛选：外文 5 + 中文 0 = 5`
3. 推送后仓库根目录的 `data/pushed_history.json` 条数增加
4. 最后一步有 `chore: 更新推送历史 (...)` 的 commit

---

## 七、日常运维

### 重置历史（想重新看一遍所有近期论文）
```bash
rm data/pushed_history.json
git add -A && git commit -m "chore: 重置推送历史" && git push
```

### 想恢复中文 3:2
```bash
# Actions 手动触发时改 input：en_quota=3, zh_quota=2
# 或改 workflow 默认值后提交
```

### 已知限制
- Actions 的 `GITHUB_TOKEN` 是仓库级 token，自动 commit 显示 `github-actions[bot]`（不是你自己）
- 连续几天没跑（cron 失败 / 仓库停用），历史停在那一天；恢复后从断点继续，不会一次性补发
- GitHub 免费版 cron 可能延迟 5-30 分钟，属正常现象

### 中文源升级路径（未来）
1. **万方开放 API**（需申请开发者账号，免费）—— 真正的权威中文源，有最新文献
2. **CNKI 开放平台**（需机构授权）
3. 接入后把 `ZH_QUOTA` 调回 `2`
