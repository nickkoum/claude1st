"""Step 7 — Reply detection and immediate human handoff."""

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText

from .config import Config
from .crm import GHLClient
from .models import Contact, OutreachRecord

logger = logging.getLogger(__name__)


def handle_reply(
    contact: Contact,
    record: OutreachRecord,
    opportunity_id: str,
    task_id: str,
    config: Config,
) -> None:
    """
    Called as soon as an inbound reply is detected from the contact.

    Actions:
      1. Mark record as replied (stops all future automated emails)
      2. Move pipeline stage to "Replied — Needs Human"
      3. Remove 'greece-hospitality-cold' tag; add 'hot-lead' tag
      4. Create urgent HIGH PRIORITY task for the GHL user
      5. Send internal email notification
    """
    record.replied = True
    replied_at = datetime.now(timezone.utc)
    date_str = replied_at.strftime("%Y-%m-%d %H:%M UTC")

    ghl = GHLClient(config)

    # Move opportunity stage
    ghl.update_opportunity_stage(opportunity_id, config.ghl_stage_replied_id)

    # Swap tags
    ghl.remove_tag(contact.id, "greece-hospitality-cold")
    ghl.add_tag(contact.id, "hot-lead")

    # Log note
    ghl.log_note(
        contact.id,
        f"Inbound reply received on {date_str}. Automated sequence STOPPED. Human handoff initiated.",
    )

    # Close existing follow-up task and create urgent one
    try:
        ghl.close_task(contact.id, task_id)
    except Exception:
        logger.warning("Could not close task %s — it may already be closed.", task_id)

    urgent_title = (
        f"{contact.display_name} from {contact.display_location} replied — take over now"
    )
    ghl.create_task(
        contact_id=contact.id,
        title=urgent_title,
        due_date=replied_at,
        assigned_to=config.ghl_user_id,
        high_priority=True,
    )

    # Send internal notification email
    _send_internal_notification(contact, config)

    logger.info(
        "Reply handoff complete for contact %s — hot-lead, human notified.",
        contact.id,
    )


def _send_internal_notification(contact: Contact, config: Config) -> None:
    """Email the team with an urgent alert that a lead replied."""
    property_label = f", {contact.property_name}" if contact.property_name else ""
    subject = (
        f"🔴 New reply: {contact.display_name} — {contact.display_location}{property_label}"
    )
    body = (
        f"New reply from {contact.display_name} — {contact.property_name or 'N/A'}, "
        f"{contact.display_location}.\n\n"
        f"Log in and respond within the hour.\n\n"
        f"Contact email: {contact.email}\n"
        f"Contact ID: {contact.id}"
    )

    msg = MIMEText(body, "plain")
    msg["From"] = config.sender_email
    msg["To"] = config.notification_email
    msg["Subject"] = subject

    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
            if config.smtp_use_tls:
                server.starttls()
            server.login(config.smtp_username, config.smtp_password)
            server.sendmail(config.sender_email, config.notification_email, msg.as_string())
        logger.info("Internal notification sent to %s.", config.notification_email)
    except Exception as exc:
        # Notification failure must not break the handoff flow
        logger.error("Failed to send internal notification: %s", exc)
