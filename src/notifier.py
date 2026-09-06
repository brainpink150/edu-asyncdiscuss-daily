"""
邮件推送模块

支持任意 SMTP 服务（QQ邮箱 / 163 / Gmail / Outlook / 学校邮箱）。
QQ 邮箱与 163 邮箱需要先在网页端开启 SMTP 服务并取得"授权码"。
"""

import logging
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from typing import Optional

logger = logging.getLogger(__name__)


def send_email(
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> bool:
    """
    通过 SMTP 发送邮件。

    配置项（环境变量）：
        SMTP_HOST       SMTP 服务器地址
        SMTP_PORT       端口（SSL 通常 465，TLS 通常 587）
        SMTP_USER       登录用户名（通常是邮箱地址）
        SMTP_PASSWORD   授权码 / 密码
        MAIL_FROM       发件人（可与 SMTP_USER 不同）
        MAIL_TO         收件人列表，英文逗号分隔
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("MAIL_FROM") or user
    to_addrs_raw = os.getenv("MAIL_TO") or user
    to_addrs = [a.strip() for a in to_addrs_raw.split(",") if a.strip()]

    missing = [k for k, v in {
        "SMTP_HOST": host, "SMTP_USER": user,
        "SMTP_PASSWORD": password, "MAIL_FROM": from_addr,
    }.items() if not v]
    if missing:
        logger.error(f"缺少邮件配置：{', '.join(missing)}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("教育技术学每日文献", from_addr))
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = formatdate(localtime=True)

    # 纯文本 + HTML 双版本，邮件客户端优先 HTML
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        # 优先 SSL（QQ/163 邮箱端口 465），失败时尝试 STARTTLS（587）
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                server.login(user, password)
                server.sendmail(from_addr, to_addrs, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.login(user, password)
                server.sendmail(from_addr, to_addrs, msg.as_string())
        logger.info(f"邮件已发送至 {to_addrs}")
        return True
    except smtplib.SMTPException as e:
        logger.error(f"邮件发送失败：{e}")
        return False
    except Exception as e:
        logger.error(f"邮件发送异常：{e}")
        return False