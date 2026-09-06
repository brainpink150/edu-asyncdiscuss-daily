# Mac 版部署教程

> 把 `edu-asyncdiscuss-daily` 项目从你的电脑推到 GitHub、配上邮件推送，每天早上 9 点准时收到 5 篇权威文献。

预计耗时：**15-20 分钟**（其中等待 GitHub 触发 + 邮箱送达约 5 分钟）。

---

## 0. 准备工作

打开「终端」（Terminal，macOS 自带，在启动台搜"Terminal"或在 Finder `应用程序/实用工具` 里）。

确认两个工具已装：

```bash
git --version
# 看到 git version 2.x 即可，macOS 自带但 Command Line Tools 没装的话会提示

gh --version
# 看到 gh version 2.x 即可，没装就装一下（见下一步）
```

如果 `gh` 没装：

```bash
brew install gh
# 没有 brew 的话先去 https://brew.sh 复制安装命令
```

---

## 1. 解压 zip 包

把下载的 `edu-asyncdiscuss-daily.zip` 放在 `~/Projects/` 下（你可以换成任何位置，下面以此为例）：

```bash
mkdir -p ~/Projects
mv ~/Downloads/edu-asyncdiscuss-daily.zip ~/Projects/
cd ~/Projects
unzip edu-asyncdiscuss-daily.zip
cd edu-asyncdiscuss-daily
ls
```

你应该看到这些文件：

```
.github/  docs/  src/  scripts/
.env.example  .gitignore  README.md
main.py  requirements.txt  test_local.py
```

> 💡 Mac 默认解压会把 zip 里的隐藏文件 `.env.example` `.gitignore` 一起解压，OK 不影响。

---

## 2. 创建 GitHub 仓库并推送

### 2.1 登录 GitHub CLI

```bash
gh auth login
```

按提示选：
- `GitHub.com`
- `HTTPS`
- `Login with a web browser`（最方便）

浏览器弹窗，点 "Authorize"。

### 2.2 创建公开仓库并推送

```bash
gh repo create edu-asyncdiscuss-daily --public --source=. --remote=origin --push --description "每日教育技术学权威文献邮件推送"
```

这条命令会：
- 在你的 GitHub 账号下建一个公开仓库
- 把当前目录作为源码
- 添加 `origin` 远程
- 直接 `git push`

完成后会打印仓库 URL，形如：
```
https://github.com/<你的用户名>/edu-asyncdiscuss-daily
```

> 💡 想建私有仓库？把 `--public` 改成 `--private`。注意：私有仓库每月只有 2000 分钟 Actions 额度，够用但要注意。

### 2.3 验证推送成功

```bash
gh repo view --web
```

浏览器应该打开你的新仓库页面，看到所有源码。

---

## 3. 开启 QQ 邮箱 SMTP 并取得授权码

> 这一步的目的：拿到一串 16 位授权码，让 GitHub Actions 能用你的 QQ 邮箱发邮件。

### 3.1 网页端开启服务

1. 浏览器打开 https://mail.qq.com 并登录
2. 顶部点「设置」→ 左侧「账户」
3. 往下滚到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务」一栏
4. 找到「IMAP/SMTP服务」，点右边的「开启」
5. 弹窗要求发送短信到指定号码，按提示发
6. 发完点「我已发送」，页面刷新后会出现一串 **授权码**，**立即复制保存**（只显示一次！）

### 3.2 备用：网易 163 邮箱

1. https://mail.163.com → 设置 → POP3/SMTP/IMAP
2. 开启「IMAP/SMTP服务」+「POP3/SMTP服务」，扫码设置授权码
3. SMTP 主机：`smtp.163.com`，端口：`465` 或 `25`

### 3.3 备用：Outlook / Gmail

- **Outlook**：`smtp.office365.com:587`（STARTTLS），用账号密码
- **Gmail**：`smtp.gmail.com:587`，需要先开两步验证，再生成"应用专用密码"

---

## 4. 在 GitHub 配置 SMTP Secrets

这一步把邮箱授权码告诉 GitHub Actions，让它能替你发邮件。

### 4.1 打开 Secrets 页面

终端里直接打开：

```bash
gh repo view --web
```

页面打开后：
- 顶部点「Settings」
- 左侧菜单找到「Secrets and variables」→「Actions」
- 点「New repository secret」

### 4.2 逐个添加 6 个 Secret

> 字段名必须完全一致（大小写敏感），Value 填你自己的值。

| Name | Value 示例 |
| --- | --- |
| `SMTP_HOST` | `smtp.qq.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | `12345678@qq.com` |
| `SMTP_PASSWORD` | `abcdefghijklmnop` ← 刚才的授权码 |
| `MAIL_FROM` | `12345678@qq.com` |
| `MAIL_TO` | `12345678@qq.com`（多个收件人用英文逗号分隔） |

**可选第 7 个**（强烈推荐）：`CONTACT_EMAIL`，填你的真实邮箱，让 OpenAlex 给你更高的 API 速率限制。

### 4.3 一键用 gh CLI 添加（推荐，省去网页操作）

```bash
# 替换成你自己的邮箱和授权码
gh secret set SMTP_HOST --body "smtp.qq.com"
gh secret set SMTP_PORT --body "465"
gh secret set SMTP_USER --body "你的QQ@qq.com"
gh secret set SMTP_PASSWORD --body "你的授权码"
gh secret set MAIL_FROM --body "你的QQ@qq.com"
gh secret set MAIL_TO --body "你的QQ@qq.com"
gh secret set CONTACT_EMAIL --body "你的QQ@qq.com"

# 验证
gh secret list
```

应该列出全部 7 个。

---

## 5. 启用并手动触发 workflow

### 5.1 启用 workflow

第一次 push 完后 GitHub 不会自动启用 workflow，需要手动开：

```bash
gh workflow enable "daily-papers.yml"
```

或者：
1. 仓库页面 → 顶部「Actions」标签
2. 如果看到红色横幅 "Workflows weren't found"，等 1-2 分钟刷新
3. 左侧应该出现「Daily Papers」

### 5.2 手动触发第一次

```bash
gh workflow run "daily-papers.yml" \
  --raw-field lookback_days=30 \
  --raw-field top_k=5
```

> `lookback_days=30` 第一次拉长回溯窗口，更容易看到效果；以后每天 7 天就够。

或者网页版：
1. Actions 页面 → 点「Daily Papers」
2. 右侧「Run workflow」按钮
3. 下拉选 `main` 分支
4. `lookback_days` 填 `30`，`top_k` 填 `5`
5. 点绿色按钮「Run workflow」

### 5.3 实时查看日志

```bash
# 等几秒后用 watch 模式查看运行状态
gh run watch
```

按 `Ctrl+C` 退出 watch 模式，但 workflow 会继续在云端跑。

要查看某个具体 step 的输出：

```bash
gh run list                  # 列出最近 10 次运行
gh run view <run-id> --log   # 查看某次运行的完整日志
```

---

## 6. 验证邮件收到

### 6.1 等待 + 检查邮箱

GitHub Actions 跑完通常 1-3 分钟。之后：
- 打开手机邮件 App 或 QQ 邮箱 App
- 查收来自你自己的 QQ 邮箱（因为 MAIL_FROM 是你自己）
- 主题形如：**教育技术学每日文献推送 · 2026-09-04**

### 6.2 如果没收到

排查顺序：

1. **垃圾邮件箱**：QQ 邮箱有时把自发自收归到「垃圾邮件」
2. **查看 Actions 日志**：
   ```bash
   gh run view --log | grep -i error
   ```
3. **看 SMTP 错误**：
   - `SMTPServerDisconnected` → 密码错 / 端口错
   - `认证失败` → 重新生成授权码
   - `connection refused` → 检查 SMTP_HOST 和 SMTP_PORT

4. **重新设置授权码**：登录 QQ 邮箱网页 → 设置 → 账户 → 关闭 SMTP 服务 → 重新开启 → 拿到新授权码 → `gh secret set SMTP_PASSWORD --body "新授权码"`

---

## 7. 调整推送时间（可选）

默认是每天北京时间 9:00（对应 UTC 1:00）。

如果要改时间，编辑 `.github/workflows/daily-papers.yml` 里这一行：

```yaml
schedule:
  - cron: "0 1 * * *"   # 当前：UTC 1:00 = 北京 9:00
```

**时区对照**（cron 用 UTC 时间）：

| 北京时间 | cron 表达式 |
| --- | --- |
| 早上 7:00 | `"0 23 * * *"` |
| 早上 8:00 | `"0 0 * * *"` |
| 早上 9:00（默认） | `"0 1 * * *"` |
| 中午 12:00 | `"0 4 * * *"` |
| 晚上 9:00 | `"0 13 * * *"` |

改完提交：

```bash
git add .github/workflows/daily-papers.yml
git commit -m "chore: 调整推送时间为晚上 9 点"
git push
```

GitHub 大约 5-15 分钟内会生效新 cron。

---

## 8. 自定义检索主题（可选）

打开 `src/fetchers/openalex.py`，找到 `KEYWORDS` 列表，加减关键词：

```python
KEYWORDS = [
    "asynchronous discussion",
    "online discussion",
    "异步讨论",
    # 想加什么就加什么，比如：
    # "AI 辅助教学",
    # "computer-supported collaborative learning",
]
```

保存后 `git push` 即可，下次跑自动用新关键词。

---

## 附：完整命令速查表

```bash
# 解压 + 推送到 GitHub（一气呵成）
cd ~/Projects
unzip ~/Downloads/edu-asyncdiscuss-daily.zip
cd edu-asyncdiscuss-daily
gh auth login
gh repo create edu-asyncdiscuss-daily --public --source=. --remote=origin --push

# 配置 Secrets
gh secret set SMTP_HOST --body "smtp.qq.com"
gh secret set SMTP_PORT --body "465"
gh secret set SMTP_USER --body "你的QQ@qq.com"
gh secret set SMTP_PASSWORD --body "你的授权码"
gh secret set MAIL_FROM --body "你的QQ@qq.com"
gh secret set MAIL_TO --body "你的QQ@qq.com"

# 触发一次 + 看日志
gh workflow run "daily-papers.yml" --raw-field lookback_days=30 --raw-field top_k=5
sleep 5
gh run watch
```

---

## 常见问题

**Q：GitHub Actions 没自动运行？**
A：先确认 cron 时间已过。GitHub 免费账户的定时任务可能延迟 5-15 分钟触发（官方说最迟 30 分钟）。可以手动触发验证 workflow 本身没问题。

**Q：私有仓库能用吗？**
A：能，但 GitHub 免费账户私有仓库每月 2000 分钟 Actions 额度。每月跑一次约 0.1 分钟，够用。

**Q：邮件能改成飞书 / 微信推送吗？**
A：能。编辑 `src/notifier.py` 加一个 `send_feishu()` 函数，在 `main.py` 里替换 `send_email()` 调用。Actions workflow 不需要改动。

**Q：怎么停止推送？**
A：
```bash
gh workflow disable "daily-papers.yml"
```

**Q：怎么删除整个项目？**
A：仓库 Settings → Danger Zone → Delete this repository。

---

跑通之后你的早晨就多了一件事：9 点打开手机邮箱看一眼当天精选。如果哪天觉得文献质量想调整（更多国内期刊、更聚焦某个子主题），改两行代码 `git push` 就好。