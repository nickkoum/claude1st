"""Steps 2 & 3 — Pain point selection and AI-powered email generation.

Uses Claude claude-opus-4-6 with adaptive thinking to craft hyper-personalised
cold outreach emails that follow the 110-word, peer-to-peer style brief.
"""

import logging
from typing import Optional

import anthropic

from .config import Config
from .models import Contact, EmailContent, PropertyType, Segment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pain points (Step 2)
# ---------------------------------------------------------------------------

PAIN_POINTS: dict[tuple, str] = {
    (PropertyType.AIRBNB_HOST, Segment.SMALL_HOST): (
        "Responding to guest inquiries manually at all hours is burning you out "
        "and costing you bookings when you reply slow"
    ),
    (PropertyType.AIRBNB_HOST, Segment.GROWTH_HOST): (
        "Managing multiple listings means guest communication falls through the "
        "cracks — reviews suffer and occupancy drops"
    ),
    (PropertyType.AIRBNB_HOST, Segment.POWER_HOST): (
        "At scale, manual operations become your ceiling — "
        "you can't grow what you can't automate"
    ),
    (PropertyType.BOUTIQUE_HOTEL, Segment.BOUTIQUE_HOTEL): (
        "Hotels your size are losing direct bookings to OTAs because the guest "
        "experience before check-in feels generic and slow"
    ),
}


def select_pain_point(contact: Contact) -> str:
    """Return the primary pain point for this contact's segment."""
    key = (contact.property_type, contact.segment)
    pain = PAIN_POINTS.get(key)
    if not pain:
        # Fallback: use boutique-hotel pain for any hotel variant, else small-host
        if contact.property_type == PropertyType.BOUTIQUE_HOTEL:
            pain = PAIN_POINTS[(PropertyType.BOUTIQUE_HOTEL, Segment.BOUTIQUE_HOTEL)]
        else:
            pain = PAIN_POINTS[(PropertyType.AIRBNB_HOST, Segment.SMALL_HOST)]
    return pain


# ---------------------------------------------------------------------------
# Email generation (Step 3)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a B2B outreach copywriter specialising in the Greek hospitality sector.
Your job is to write cold emails that feel like they were written by a peer — \
direct, warm, and never salesy.

STRICT rules you must follow every time:
1. Maximum 110 words in the email body (not counting subject line).
2. Open with the recipient's first name and a location-specific or \
   property-specific observation. NEVER use "I hope this email finds you well."
3. Sentence 2: name the pain point directly, as if you already know their operation.
4. Sentences 3-4: introduce the OUTCOME we deliver (more bookings, less manual \
   work, better reviews, more time) — NOT features.
5. Final line: one soft CTA inviting a 15-minute call, zero-pressure framing.
6. Tone: peer-to-peer, direct, warm — NOT salesy.
7. Do NOT mention price, packages, or company taglines.
8. Do NOT use bullet points inside the email body.
9. Sign off with the sender's first name only.
10. Subject line: max 6 words, creates curiosity or references location/property, \
    no emojis, no questions.

Return ONLY the following format — nothing else:
Subject: <subject line>
Body: <email body>
"""


def _build_user_prompt(contact: Contact, pain_point: str, sender_first_name: str) -> str:
    name = contact.display_name
    location = contact.display_location
    property_ref = f" (property: {contact.property_name})" if contact.property_name else ""
    property_type_label = (
        "boutique hotel" if contact.property_type == PropertyType.BOUTIQUE_HOTEL
        else "Airbnb host"
    )
    segment_label = contact.segment.value if contact.segment else "host"

    return (
        f"Write a cold outreach email for:\n"
        f"- Recipient first name: {name}\n"
        f"- Location: {location}\n"
        f"- Property type: {property_type_label}{property_ref}\n"
        f"- Segment: {segment_label}\n"
        f"- Pain point to lead with: {pain_point}\n"
        f"- Sender's first name (sign-off): {sender_first_name}\n"
    )


def _parse_email_response(raw: str) -> tuple[str, str]:
    """
    Parse the model response into (subject, body).
    Expected format:
        Subject: <subject line>
        Body: <email body>
    """
    subject = ""
    body_lines: list[str] = []
    in_body = False

    for line in raw.strip().splitlines():
        if line.startswith("Subject:") and not in_body:
            subject = line[len("Subject:"):].strip()
        elif line.startswith("Body:"):
            in_body = True
            remainder = line[len("Body:"):].strip()
            if remainder:
                body_lines.append(remainder)
        elif in_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    if not subject or not body:
        raise ValueError(
            f"Could not parse Subject/Body from model response:\n{raw}"
        )
    return subject, body


def generate_email(contact: Contact, config: Config) -> EmailContent:
    """
    Generate a personalised cold email for the contact using Claude.

    Returns an EmailContent with subject, body, and the pain point used.
    """
    pain_point = select_pain_point(contact)
    user_prompt = _build_user_prompt(contact, pain_point, config.sender_first_name)

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    logger.info("Generating email for contact %s via Claude ...", contact.id)

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=512,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        response = stream.get_final_message()

    raw_text = next(
        (block.text for block in response.content if block.type == "text"),
        "",
    )

    subject, body = _parse_email_response(raw_text)

    logger.info(
        "Email generated for contact %s — subject: '%s'", contact.id, subject
    )

    return EmailContent(subject=subject, body=body, pain_point=pain_point)
