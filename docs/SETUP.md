# 配置指南

本文档手把手教你把这个项目部署到自己的 GitHub 账号上，从 0 到跑通。

## 1. 创建 GitHub 仓库

1. 登录 GitHub，点击右上角 `+` → `New repository`
2. Repository name` 填：`edu-asyncdiscuss-daily`（或自取）
3. 选择 `Public`（开源）或 `Private`（私有）
4. **不要**勾选 `Add a README`，本地工程已经包含了
5. 点击 `Create repository`

把代码推到新仓库：

```bash
cd edu-asyncdiscuss-daily
git init
git add .
git commit -m "feat: 初始化每日文献推送项目"
git branch -M main
git remote add origin https://github.com/<your-username>/edu-asyncdiscuss-daily.git
git push -u origin main
```

## 2. 准备 SMTP 邮箱（以 QQ邮箱 为例）

### QQ邮箱
1. 登录 [QQ邮箱网页版](https://mail.qq.com)
2. 顶部 `设置` → `账户` → 往下找到 `POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务`
3. 开启 `SMTP服务`，按提示**发送短信**验证
4. 验证成功后页面会显示一串**授权码**，复制保存（只显示一次）
5. 配置：
   - SMTP 主机：`smtp.qq.com`
   - 端口：`465`
   - 用户名：`你的QQ@qq.com`
   - 密码：**授权码**（不是 QQ 密码）

### 网易163邮箱
1. 登录 [163邮箱](https://mail.163.com)
2. `设置` → `POP3/SMTP/IMAP`
3. 开启 `IMAP/SMTP服务` 和 `POP3/SMTP服务`，设置**授权码**
4. 配置：
   - SMTP 主机：`smtp.163.com`
   - 端口：`465` 或 `25`
   - 用户名：`你的用户名@163.com`
   - 密码：**授权码**

### Outlook / Gmail
- Outlook：`smtp.office365.com:587` (STARTTLS)
- Gmail：`smtp.gmail.com:587`，需要"应用专用密码"

## 3. 在 GitHub 配置 Secrets

1. 进入你刚创建的仓库页面
2. `Settings` → `Secrets and variables` → `Actions`
3. 点击 `New repository secret`，**逐个添加**以下 6 个：

| Name | Value 示例 |
| --- | --- |
| `SMTP_HOST` | `smtp.qq.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | `your_email@qq.com` |
| `SMTP_PASSWORD` | `你的授权码` |
| `MAIL_FROM` | `your_email@qq.com` |
| `MAIL_TO` | `your_email@qq.com`（多个用英文逗号分隔） |

可选第 7 个：`CONTACT_EMAIL` —— 填你自己的邮箱，让 OpenAlex 给你更高的速率限制。

> ⚠️ Secrets 一旦保存无法再次查看，丢失只能重新填写。

## 4. 启用 GitHub Actions

1. 仓库页面 → 顶部 `Actions` 标签
2. 如果看到提示 "Workflows weren't found in this repository"，说明你已经成功推送 `.github/workflows/daily-papers.yml`，但 GitHub 需要几分钟发现
3. 等 1-2 分钟刷新页面，应该会看到左侧的 `Daily Papers` workflow
4. 点击 → `Enable workflow`

## 5. 手动触发一次测试

1. 在 `Actions` 页面，点击 `Daily Papers`
2. 右侧 `Run workflow` → 下拉选 `main` 分支
3. `lookback_days` 填 `30`（首次测试建议拉长回溯窗口）
4. `top_k` 填 `5`
5. 点击绿色按钮 `Run workflow`

### 如何查看运行结果
- 进入对应的运行记录
- 展开 `Run daily pipeline` 这一步，看日志
- 如果成功，几分钟后邮箱会收到 HTML 邮件

### 常见问题
- **SMTPServerDisconnected**：密码错 / 端口错 / 没开 SMTP 服务
- **认证失败**：授权码失效，重新生成
- **网络超时**：GitHub Actions 海外服务器访问国内邮箱可能慢，重试即可
- **每天没收到邮件**：检查 cron 表达式（`0 1 * * *` 是 UTC 时间，北京时间需要减 8 小时）

## 6. 时区调整

`.github/workflows/daily-papers.yml` 中：

```yaml
schedule:
  - cron: "0 1 * * *"   # = 北京 9:00
```

改成你想的时间。例如：
- 北京时间 8:00 → `"0 0 * * *"`
- 北京时间 7:30 → `"30 23 * * *"`（前一晚 UTC 23:30）

## 7. 本地调试

```bash
# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 复制环境变量模板
cp .env.example .env
# 编辑 .env 填写真实 SMTP 配置

# 直接运行（不会真的发邮件，先把 SMTP_PASSWORD 留空测试检索）
python main.py

# 查看生成的归档
cat archive/2026-09-04.md
cat logs/summary.json
```

## 8. 进阶：更换推送渠道

如果你之后想从邮件切换到其他渠道（飞书/Telegram/微信），只需要：

1. 在 `src/notifier.py` 里加一个新的推送函数（如 `send_feishu()`）
2. 在 `main.py` 里替换 `send_email(...)` 调用

工作流无需改动。

## 9. 数据准确性说明

- OpenAlex 数据来自 Crossref，覆盖范围比 Web of Science 略小（含 WoS 约 95% 的期刊）
- 关键词检索用 title + abstract 全文匹配，可能漏掉只出现在正文里的相关文献
- 中文期刊在 OpenAlex 中的元数据完整性低于英文期刊，可考虑未来接 CNKI 检索增强
- 如果某天确实没有新文献，会跳过邮件推送，不发"空邮件"

---

需要更多帮助？提 Issue 或看 [README.md](../README.md)。