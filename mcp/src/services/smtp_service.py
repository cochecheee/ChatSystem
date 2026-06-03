"""SMTP service — V2.4 alert email sending.

Graceful no-op when SMTP_HOST is empty so the rest of the monitor pipeline
keeps working without email setup. For real production use Gmail App
Password (https://myaccount.google.com/apppasswords) or Mailtrap sandbox.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..core.config import settings

log = logging.getLogger(__name__)


def send_alert_email(*, subject: str, body_html: str, body_text: str = "") -> bool:
    """Send 1 alert email. Returns True if dispatched, False if skipped/failed.

    Skip conditions (silent, no log noise):
    - settings.SMTP_HOST empty
    - settings.EMAIL_TO empty
    """
    if not settings.SMTP_HOST or not settings.EMAIL_TO:
        log.debug("SMTP not configured — email skipped")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER or "alerts@chat-system.local"
    msg["To"] = settings.EMAIL_TO
    msg.set_content(body_text or _html_to_text(body_html))
    msg.add_alternative(body_html, subtype="html")

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as srv:
            if settings.SMTP_USE_TLS:
                srv.starttls()
            if settings.SMTP_USER and settings.SMTP_PASS:
                srv.login(settings.SMTP_USER, settings.SMTP_PASS)
            srv.send_message(msg)
        log.info("Sent alert email to %s: %s", settings.EMAIL_TO, subject)
        return True
    except Exception:
        log.exception("Failed to send alert email — continuing without")
        return False


def _html_to_text(html: str) -> str:
    """Crude HTML strip for the text alternative."""
    import re
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def format_down_alert(*, target_url: str, fail_count: int, last_status: int) -> tuple[str, str]:
    """Return (subject, body_html) for a 'service down' alert."""
    subject = f"[chat-system] DOWN: {target_url}"
    body = f"""
    <h2 style="color: #c62828;">Service Down Alert</h2>
    <p>Monitor detected {fail_count} consecutive failed health checks for:</p>
    <p><a href="{target_url}">{target_url}</a></p>
    <ul>
      <li><b>Last HTTP status:</b> {last_status if last_status else "no response"}</li>
      <li><b>Consecutive failures:</b> {fail_count}</li>
    </ul>
    <p style="color: #888; font-size: 12px;">
      Sent by chat-system monitor. Acknowledge in the dashboard's Monitor tab.
    </p>
    """
    return subject, body


def format_recovered_alert(*, target_url: str, downtime_minutes: int) -> tuple[str, str]:
    subject = f"[chat-system] RECOVERED: {target_url}"
    body = f"""
    <h2 style="color: #2e7d32;">Service Recovered</h2>
    <p>Monitor sees a 2xx response again after ~{downtime_minutes} minute(s) of downtime:</p>
    <p><a href="{target_url}">{target_url}</a></p>
    """
    return subject, body
