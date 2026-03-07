"""
Greece Hospitality Lead Engine — main orchestrator.

Coordinates all 7 steps for a single contact or a batch of contacts.

Usage (programmatic):
    from greece_hospitality_agent.agent import process_contact
    from greece_hospitality_agent.models import Contact, PropertyType

    contact = Contact(
        id="ghl-contact-id",
        email="host@example.com",
        property_type=PropertyType.AIRBNB_HOST,
        first_name="Kostas",
        property_name="Villa Sunset",
        location="Santorini",
        listing_count=2,
    )
    record = process_contact(contact, config)

Usage (CLI):
    python -m greece_hospitality_agent --help
"""

import logging
from datetime import datetime, timezone

from .config import Config
from .crm import GHLClient, post_send_crm_actions
from .email_generator import generate_email
from .email_sender import send_email
from .lead_enrichment import TRIGGER_TAG, DO_NOT_CONTACT_TAG, enrich_contact
from .models import Contact, OutreachRecord, PropertyType

logger = logging.getLogger(__name__)


def process_contact(contact: Contact, config: Config) -> OutreachRecord:
    """
    Run all 7 pipeline steps for a single contact.

    Steps:
      1. Lead enrichment & segmentation
      2. Pain point selection        (inside generate_email)
      3. Email generation via Claude (inside generate_email)
      4. Send email
      5. CRM actions
      6. Follow-up sequence is *scheduled* — call send_follow_up_1 / _2
         after the appropriate delays from the returned OutreachRecord.
      7. Reply detection is event-driven — call handle_reply when a reply
         comes in, passing the OutreachRecord returned here.

    Returns an OutreachRecord that callers must persist for follow-up scheduling.
    """
    logger.info("=== Processing contact %s ===", contact.id)

    # Guard: never send to do-not-contact
    if DO_NOT_CONTACT_TAG in contact.tags:
        raise ValueError(
            f"Contact {contact.id} is tagged '{DO_NOT_CONTACT_TAG}' — aborting."
        )

    # Guard: never fabricate — require at minimum an email
    if not contact.email:
        raise ValueError(f"Contact {contact.id} has no email address — aborting.")

    # Step 1 — Enrich
    contact = enrich_contact(contact)

    # Steps 2 & 3 — Generate email
    email_content = generate_email(contact, config)

    # Store generated content on contact for CRM custom fields
    contact.outreach_subject = email_content.subject
    contact.outreach_body = email_content.body

    # Step 4 — Send
    sent_at = datetime.now(timezone.utc)
    send_email(contact, email_content, config)

    # Update GHL contact with outreach_subject / outreach_body / tags
    ghl = GHLClient(config)
    ghl.update_contact_fields(contact)

    # Step 5 — CRM actions
    crm_result = post_send_crm_actions(contact, email_content, config, sent_at)

    record = OutreachRecord(
        contact_id=contact.id,
        email_sent_at=sent_at,
        segment=contact.segment,
        pain_point=email_content.pain_point,
    )

    logger.info(
        "=== Contact %s processed successfully. "
        "Opportunity: %s | Task: %s ===",
        contact.id,
        crm_result["opportunity_id"],
        crm_result["task_id"],
    )

    # Attach IDs to record so callers can use them for follow-ups / reply handoff
    record._opportunity_id = crm_result["opportunity_id"]  # type: ignore[attr-defined]
    record._task_id = crm_result["task_id"]               # type: ignore[attr-defined]

    return record
