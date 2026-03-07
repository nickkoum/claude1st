"""Data models for the Greece Hospitality Lead Engine."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PropertyType(str, Enum):
    AIRBNB_HOST = "airbnb_host"
    BOUTIQUE_HOTEL = "boutique_hotel"


class Segment(str, Enum):
    SMALL_HOST = "small-host"
    GROWTH_HOST = "growth-host"
    POWER_HOST = "power-host"
    BOUTIQUE_HOTEL = "boutique-hotel"


class LanguagePreference(str, Enum):
    EN = "EN"
    GR = "GR"


class OutreachStage(str, Enum):
    EMAILED_AWAITING_REPLY = "Emailed — Awaiting Reply"
    REPLIED_NEEDS_HUMAN = "Replied — Needs Human"
    SEQUENCE_COMPLETE_NO_REPLY = "Sequence Complete — No Reply"


@dataclass
class Contact:
    id: str
    email: str
    property_type: PropertyType
    first_name: Optional[str] = None
    property_name: Optional[str] = None
    location: Optional[str] = None
    listing_count: Optional[int] = None
    language_preference: LanguagePreference = LanguagePreference.EN
    segment: Optional[Segment] = None
    outreach_subject: Optional[str] = None
    outreach_body: Optional[str] = None
    tags: list = field(default_factory=list)
    created_at: Optional[datetime] = None

    @property
    def display_name(self) -> str:
        return self.first_name or "there"

    @property
    def display_location(self) -> str:
        return self.location or "Greece"


@dataclass
class EmailContent:
    subject: str
    body: str
    pain_point: str


@dataclass
class OutreachRecord:
    contact_id: str
    email_sent_at: datetime
    segment: Segment
    pain_point: str
    follow_up_1_sent_at: Optional[datetime] = None
    follow_up_2_sent_at: Optional[datetime] = None
    replied: bool = False
    unsubscribed: bool = False
