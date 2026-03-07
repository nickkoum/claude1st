"""Step 1 — Lead enrichment and segmentation."""

import logging
from .models import Contact, PropertyType, Segment

logger = logging.getLogger(__name__)

# Tag applied when this agent processed the contact
TRIGGER_TAG = "greece-hospitality-cold"
DO_NOT_CONTACT_TAG = "do-not-contact"


def assign_segment(contact: Contact) -> Segment:
    """
    Determine segment based on property_type and listing_count.

    Rules:
      - boutique_hotel                  → boutique-hotel
      - airbnb_host, 1-2 listings       → small-host
      - airbnb_host, 3-9 listings       → growth-host
      - airbnb_host, 10+ listings       → power-host
      - airbnb_host, unknown count      → small-host (safe default)
    """
    if contact.property_type == PropertyType.BOUTIQUE_HOTEL:
        return Segment.BOUTIQUE_HOTEL

    count = contact.listing_count or 1
    if count >= 10:
        return Segment.POWER_HOST
    elif count >= 3:
        return Segment.GROWTH_HOST
    else:
        return Segment.SMALL_HOST


def enrich_contact(contact: Contact) -> Contact:
    """
    Apply segment tag to the contact and return the updated contact.
    Raises ValueError if the contact carries a do-not-contact tag.
    """
    if DO_NOT_CONTACT_TAG in contact.tags:
        raise ValueError(
            f"Contact {contact.id} is tagged '{DO_NOT_CONTACT_TAG}' — skipping."
        )

    segment = assign_segment(contact)
    contact.segment = segment

    segment_tag = segment.value
    if segment_tag not in contact.tags:
        contact.tags.append(segment_tag)

    logger.info(
        "Contact %s enriched → segment=%s location=%s",
        contact.id,
        segment.value,
        contact.display_location,
    )
    return contact
