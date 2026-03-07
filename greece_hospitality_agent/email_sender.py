"""Step 4 — Send the outreach email via SMTP with open/click tracking headers."""

import logging
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import Config
from .models import Contact, EmailContent

logger = logging.getLogger(__name__)


def send_email(
    contact: Contact,
    content: EmailContent,
    config: Config,
) -> str:
    """
    Send the personalised cold email to the contact.

    Returns the Message-ID of the sent email.
    Open/click tracking is enabled by injecting standard headers;
    your ESP (e.g. SendGrid, Mailgun) can also intercept these at relay level.
    """
    msg = MIMEMultipart("alternative")
    message_id = f"<{uuid.uuid4()}@{config.sender_email.split('@')[-1]}>"

    msg["Message-ID"] = message_id
    msg["From"] = f"{config.sender_display_name} <{config.sender_email}>"
    msg["To"] = contact.email
    msg["Subject"] = content.subject

    # Open-tracking pixel placeholder — your ESP replaces this at relay level.
    # If sending directly (no ESP), remove the pixel line below.
    tracking_pixel = (
        f'<img src="https://track.yourdomain.com/open/{contact.id}" '
        f'width="1" height="1" alt="" style="display:none" />'
    )

    html_body = (
        f"<html><body>"
        f"<p>{content.body.replace(chr(10), '<br>')}</p>"
        f"{tracking_pixel}"
        f"</body></html>"
    )
    plain_body = content.body

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        if config.smtp_use_tls:
            server.starttls()
        server.login(config.smtp_username, config.smtp_password)
        server.sendmail(config.sender_email, contact.email, msg.as_string())

    logger.info(
        "Email sent to %s (contact %s) — message-id: %s",
        contact.email,
        contact.id,
        message_id,
    )
    return message_id


def send_follow_up(
    contact: Contact,
    subject: str,
    body: str,
    config: Config,
) -> str:
    """Send a follow-up email (same mechanics, different content)."""
    content = EmailContent(subject=subject, body=body, pain_point="")
    return send_email(contact, content, config)
