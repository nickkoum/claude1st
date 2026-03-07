"""Step 6 — Automated follow-up sequence (Follow-Up #1 and #2)."""

import logging
from datetime import datetime, timezone

from .config import Config
from .crm import GHLClient
from .email_sender import send_follow_up
from .models import Contact, OutreachRecord

logger = logging.getLogger(__name__)


def _build_follow_up_1(contact: Contact, sender_first_name: str) -> tuple[str, str]:
    subject = f"Still relevant, {contact.display_name}?"
    body = (
        f"Hey {contact.display_name} — just bumping this up in case it got buried.\n\n"
        f"A lot of hosts in {contact.display_location} are dealing with the same thing right now. "
        f"If the timing isn't right, no worries at all — just let me know and I'll leave you alone.\n\n"
        f"But if you're open to a quick 15 minutes, I think you'd find it useful.\n\n"
        f"{sender_first_name}"
    )
    return subject, body


def _build_follow_up_2(contact: Contact, sender_first_name: str) -> tuple[str, str]:
    subject = "Closing the loop"
    property_ref = f"with {contact.property_name}" if contact.property_name else ""
    body = (
        f"Hey {contact.display_name} — I'll keep this short.\n\n"
        f"I'll assume the timing isn't right and won't reach out again after this. "
        f"If anything changes{' ' + property_ref if property_ref else ''}, the door's open.\n\n"
        f"{sender_first_name}"
    )
    return subject, body


def send_follow_up_1(
    contact: Contact,
    record: OutreachRecord,
    config: Config,
) -> None:
    """
    Send Follow-Up #1 (3 days after initial send).
    Skips if the contact has already replied or unsubscribed.
    """
    if record.replied or record.unsubscribed:
        logger.info(
            "Skipping follow-up #1 for contact %s (replied=%s, unsubscribed=%s).",
            contact.id,
            record.replied,
            record.unsubscribed,
        )
        return

    subject, body = _build_follow_up_1(contact, config.sender_first_name)
    send_follow_up(contact, subject, body, config)
    record.follow_up_1_sent_at = datetime.now(timezone.utc)

    ghl = GHLClient(config)
    ghl.log_note(
        contact.id,
        f"Follow-up #1 sent on {record.follow_up_1_sent_at.strftime('%Y-%m-%d %H:%M UTC')}.",
    )
    logger.info("Follow-up #1 sent for contact %s.", contact.id)


def send_follow_up_2(
    contact: Contact,
    record: OutreachRecord,
    opportunity_id: str,
    task_id: str,
    config: Config,
) -> None:
    """
    Send Follow-Up #2 / final touch (7 days after initial send).
    Skips if the contact has already replied or unsubscribed.
    After sending, moves contact to 'Sequence Complete — No Reply' and closes task.
    """
    if record.replied or record.unsubscribed:
        logger.info(
            "Skipping follow-up #2 for contact %s (replied=%s, unsubscribed=%s).",
            contact.id,
            record.replied,
            record.unsubscribed,
        )
        return

    subject, body = _build_follow_up_2(contact, config.sender_first_name)
    send_follow_up(contact, subject, body, config)
    record.follow_up_2_sent_at = datetime.now(timezone.utc)

    ghl = GHLClient(config)
    ghl.log_note(
        contact.id,
        f"Follow-up #2 (final) sent on {record.follow_up_2_sent_at.strftime('%Y-%m-%d %H:%M UTC')}.",
    )

    # Move to sequence-complete stage
    ghl.update_opportunity_stage(opportunity_id, config.ghl_stage_complete_id)

    # Tag as nurture-later
    ghl.add_tag(contact.id, "nurture-later")

    # Close the open follow-up task
    ghl.close_task(contact.id, task_id)

    logger.info(
        "Follow-up #2 sent and sequence completed for contact %s.", contact.id
    )
