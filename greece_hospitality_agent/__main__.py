"""
CLI entry point: python -m greece_hospitality_agent

Modes
-----
process   Process a single contact (JSON input).
followup  Check and send pending follow-ups from a JSON records file.
reply     Mark a contact as replied and trigger human handoff.

Examples
--------
# Process a single new lead
python -m greece_hospitality_agent process \\
    --id "ghl-123" \\
    --email "kostas@example.com" \\
    --type airbnb_host \\
    --first_name Kostas \\
    --property "Villa Sunset" \\
    --location Santorini \\
    --listings 2

# Send follow-ups for contacts whose timer has expired (reads records.json)
python -m greece_hospitality_agent followup --records records.json

# Handle a reply for contact ghl-123
python -m greece_hospitality_agent reply \\
    --id ghl-123 \\
    --records records.json
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .agent import process_contact
from .config import load_config
from .follow_up import send_follow_up_1, send_follow_up_2
from .models import Contact, LanguagePreference, OutreachRecord, PropertyType, Segment
from .reply_handler import handle_reply

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Record persistence helpers (simple JSON file — swap for DB in production)
# ---------------------------------------------------------------------------

def load_records(path: str) -> dict[str, dict]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open() as f:
        return json.load(f)


def save_records(path: str, records: dict[str, dict]) -> None:
    with open(path, "w") as f:
        json.dump(records, f, default=str, indent=2)


def record_to_dict(r: OutreachRecord) -> dict:
    return {
        "contact_id": r.contact_id,
        "email_sent_at": r.email_sent_at.isoformat(),
        "segment": r.segment.value if r.segment else None,
        "pain_point": r.pain_point,
        "follow_up_1_sent_at": r.follow_up_1_sent_at.isoformat() if r.follow_up_1_sent_at else None,
        "follow_up_2_sent_at": r.follow_up_2_sent_at.isoformat() if r.follow_up_2_sent_at else None,
        "replied": r.replied,
        "unsubscribed": r.unsubscribed,
        "opportunity_id": getattr(r, "_opportunity_id", ""),
        "task_id": getattr(r, "_task_id", ""),
    }


def dict_to_record(d: dict) -> OutreachRecord:
    r = OutreachRecord(
        contact_id=d["contact_id"],
        email_sent_at=datetime.fromisoformat(d["email_sent_at"]),
        segment=Segment(d["segment"]) if d.get("segment") else None,
        pain_point=d.get("pain_point", ""),
    )
    r.follow_up_1_sent_at = (
        datetime.fromisoformat(d["follow_up_1_sent_at"])
        if d.get("follow_up_1_sent_at")
        else None
    )
    r.follow_up_2_sent_at = (
        datetime.fromisoformat(d["follow_up_2_sent_at"])
        if d.get("follow_up_2_sent_at")
        else None
    )
    r.replied = d.get("replied", False)
    r.unsubscribed = d.get("unsubscribed", False)
    r._opportunity_id = d.get("opportunity_id", "")  # type: ignore[attr-defined]
    r._task_id = d.get("task_id", "")                # type: ignore[attr-defined]
    return r


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_process(args: argparse.Namespace) -> None:
    config = load_config()

    contact = Contact(
        id=args.id,
        email=args.email,
        property_type=PropertyType(args.type),
        first_name=args.first_name or None,
        property_name=args.property or None,
        location=args.location or None,
        listing_count=args.listings or None,
        language_preference=LanguagePreference(args.lang) if args.lang else LanguagePreference.EN,
    )

    record = process_contact(contact, config)

    records = load_records(args.records)
    records[contact.id] = record_to_dict(record)
    save_records(args.records, records)

    print(f"✓ Contact {contact.id} processed. Record saved to {args.records}.")


def cmd_followup(args: argparse.Namespace) -> None:
    config = load_config()
    records_data = load_records(args.records)
    now = datetime.now(timezone.utc)
    updated = False

    for contact_id, data in records_data.items():
        record = dict_to_record(data)

        if record.replied or record.unsubscribed:
            continue

        # Build a minimal Contact for the email templates
        contact = Contact(
            id=contact_id,
            email=data.get("email", ""),
            property_type=PropertyType.AIRBNB_HOST,  # stored in records if needed
        )
        # Restore name/location from records file if stored
        contact.first_name = data.get("first_name")
        contact.location = data.get("location")
        contact.property_name = data.get("property_name")

        opp_id: str = getattr(record, "_opportunity_id", "")
        task_id: str = getattr(record, "_task_id", "")

        # Follow-up #1: 3 days after initial send
        if (
            record.follow_up_1_sent_at is None
            and now >= record.email_sent_at + timedelta(days=3)
        ):
            send_follow_up_1(contact, record, config)
            updated = True

        # Follow-up #2: 7 days after initial send (3 + 4)
        elif (
            record.follow_up_2_sent_at is None
            and record.follow_up_1_sent_at is not None
            and now >= record.email_sent_at + timedelta(days=7)
        ):
            send_follow_up_2(contact, record, opp_id, task_id, config)
            updated = True

        if updated:
            records_data[contact_id] = record_to_dict(record)

    if updated:
        save_records(args.records, records_data)
        print("✓ Follow-ups processed and records updated.")
    else:
        print("No follow-ups due at this time.")


def cmd_reply(args: argparse.Namespace) -> None:
    config = load_config()
    records_data = load_records(args.records)

    if args.id not in records_data:
        print(f"Error: contact {args.id} not found in {args.records}.", file=sys.stderr)
        sys.exit(1)

    data = records_data[args.id]
    record = dict_to_record(data)

    contact = Contact(
        id=args.id,
        email=data.get("email", ""),
        property_type=PropertyType.AIRBNB_HOST,
    )
    contact.first_name = data.get("first_name")
    contact.location = data.get("location")
    contact.property_name = data.get("property_name")

    opp_id: str = getattr(record, "_opportunity_id", "")
    task_id: str = getattr(record, "_task_id", "")

    handle_reply(contact, record, opp_id, task_id, config)

    records_data[args.id] = record_to_dict(record)
    save_records(args.records, records_data)

    print(f"✓ Reply handled for contact {args.id}. Human notified.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Greece Hospitality Lead Engine CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- process ---
    p_proc = sub.add_parser("process", help="Process a single new contact")
    p_proc.add_argument("--id", required=True, help="GHL contact ID")
    p_proc.add_argument("--email", required=True, help="Contact email address")
    p_proc.add_argument(
        "--type", required=True,
        choices=["airbnb_host", "boutique_hotel"],
        help="Property type",
    )
    p_proc.add_argument("--first_name", default="", help="Contact first name")
    p_proc.add_argument("--property", default="", help="Property name")
    p_proc.add_argument("--location", default="", help="City or island in Greece")
    p_proc.add_argument("--listings", type=int, default=0, help="Number of listings")
    p_proc.add_argument("--lang", default="EN", choices=["EN", "GR"], help="Language preference")
    p_proc.add_argument("--records", default="records.json", help="Records file path")

    # --- followup ---
    p_fu = sub.add_parser("followup", help="Send pending follow-up emails")
    p_fu.add_argument("--records", default="records.json", help="Records file path")

    # --- reply ---
    p_reply = sub.add_parser("reply", help="Handle an inbound reply from a contact")
    p_reply.add_argument("--id", required=True, help="GHL contact ID")
    p_reply.add_argument("--records", default="records.json", help="Records file path")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "process":
        cmd_process(args)
    elif args.command == "followup":
        cmd_followup(args)
    elif args.command == "reply":
        cmd_reply(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
