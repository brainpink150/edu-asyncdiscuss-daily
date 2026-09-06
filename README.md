# 📚 教育技术学·异步讨论 每日文献推送

> 每天早上 9:00（北京时间），自动从权威期刊中筛选 5 篇与「在线异步讨论」主题相关的最新文献，推送到你的邮箱。

[![daily](https://img.shields.io/badge/schedule-every%20day%2009:00-blue)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-green)]()
[![License](https://img.shields.io/badge/license-MIT-orange)]()

## 项目亮点

- **期刊权威**：覆盖 10 本国际 SSCI 教育技术学顶刊 + 8 本国内 CSSCI / 北大核心
- **主题聚焦**：以「asynchronous discussion / 异步讨论」为核心关键词，过滤掉无关文献
- **数据可靠**：用 [OpenAlex](https://openalex.org) 做主数据源，覆盖范围接近 Web of Science；[Crossref](https://www.crossref.org) 作兜底
- **零成本**：GitHub Actions 免费额度足够每天一次任务；OpenAlex / Crossref API 都不需要密钥
- **零服务器**：邮件直接通过 SMTP 发送，无需中间服务

## 监控期刊清单

### 国际 SSCI 教育技术学顶刊
| 期刊 | ISSN | 出版社 |
| --- | --- | --- |
| Educational Technology Research and Development | 1042-1629 | Springer |
| Computers & Education | 0360-1315 | Elsevier |
| Internet and Higher Education | 1096-7516 | Elsevier |
| British Journal of Educational Technology | 0007-1013 | Wiley |
| Journal of Computer Assisted Learning | 0266-4909 | Wiley |
| Educational Technology & Society | 1176-3647 | IEEE |
| American Journal of Distance Education | 0892-3647 | T&F |
| Distance Education | 0158-7919 | T&F |
| Learning and Instruction | 0959-4752 | Elsevier |
| Journal of Educational Technology & Online Learning | 2636-8404 | JETOL |

### 国内 CSSCI / 北大核心
| 期刊 | ISSN | 主办 |
| --- | --- | --- |
| 电化教育研究 | 1003-1553 | 西北师范大学 |
| 中国远程教育 | 1009-4583 | 国家开放大学 |
| 开放教育研究 | 1007-2179 | 上海远程教育集团 |
| 现代教育技术 | 1009-8097 | 清华大学 |
| 现代远程教育研究 | 1009-5198 | 四川开放大学 |
| 远程教育杂志 | 1672-0008 | 浙江开放大学 |
| 中国电化教育 | 1006-9860 | 中央电化教育馆 |
| 教育技术研究 | 1671-489X | 天津电化教育馆 |

> 想增减期刊？编辑 `src/fetchers/journals.py` 里的列表即可。

## 快速开始

```bash
git clone https://github.com/<your-username>/edu-asyncdiscuss-daily.git
cd edu-asyncdiscuss-daily
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 SMTP 配置
python main.py
```

### GitHub Actions 部署步骤
详见 [docs/SETUP.md](docs/SETUP.md)：仓库创建 → Secrets 配置 → 启用 Actions。

### 推荐邮箱
- **QQ邮箱**：开启 SMTP → 取得授权码 → `smtp.qq.com:465`
- **网易163**：开启 SMTP → 取得授权码 → `smtp.163.com:465`
- **Outlook / Gmail**：端口 587，使用 STARTTLS

## 文件结构

```
edu-asyncdiscuss-daily/
├── .github/workflows/daily-papers.yml   # GitHub Actions 定时任务
├── src/
│   ├── fetchers/
│   │   ├── journals.py                  # 权威期刊清单
│   │   ├── openalex.py                  # OpenAlex 主检索
│   │   └── crossref.py                  # Crossref 兜底检索
│   ├── formatter.py                     # HTML / Markdown 渲染
│   └── notifier.py                      # SMTP 邮件推送
├── main.py                              # 主入口
├── requirements.txt
├── .env.example
└── docs/SETUP.md                        # 详细配置指南
```

## 工作原理

```
GitHub Actions cron (UTC 1:00 = 北京 9:00)
        ↓
   main.py
        ↓
OpenAlex 检索 ──失败→ Crossref 兜底
   ISSN 过滤 + 关键词搜索
        ↓
   标准化 → 去重 → 相关性排序
        ↓
   HTML 格式化 + Markdown 归档
        ↓
   SMTP 发送 → 手机邮箱推送
```

## 自定义检索主题

编辑 `src/fetchers/openalex.py` 中的 `KEYWORDS` 列表：

```python
KEYWORDS = [
    "asynchronous discussion",
    "online discussion",
    "异步讨论",
    # 加入你自己的关键词...
]
```

## License

MIT License

## 致谢

- [OpenAlex](https://openalex.org) —— 开放的学术文献索引
- [Crossref](https://www.crossref.org) —— DOI 元数据基金会
- GitHub Actions —— 免费定时任务