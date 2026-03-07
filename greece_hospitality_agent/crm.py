"""Step 5 — GoHighLevel CRM actions: pipeline move, note logging, task creation."""

import logging
from datetime import datetime, timedelta, timezone

import requests

from .config import Config
from .models import Contact, EmailContent, OutreachStage, Segment

logger = logging.getLogger(__name__)

GHL_BASE_URL = "https://rest.gohighlevel.com/v1"


class GHLClient:
    """Thin wrapper around the GoHighLevel REST API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._headers = {
            "Authorization": f"Bearer {config.ghl_api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28",
        }

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    def update_contact_fields(
        self,
        contact: Contact,
        extra_fields: dict | None = None,
    ) -> None:
        """Persist custom fields (outreach_subject, outreach_body) and tags."""
        payload: dict = {
            "tags": contact.tags,
            "customField": [
                {"id": "outreach_subject", "value": contact.outreach_subject or ""},
                {"id": "outreach_body", "value": contact.outreach_body or ""},
            ],
        }
        if extra_fields:
            payload.update(extra_fields)

        url = f"{GHL_BASE_URL}/contacts/{contact.id}"
        resp = requests.put(url, json=payload, headers=self._headers, timeout=15)
        resp.raise_for_status()
        logger.info("Contact %s fields updated in GHL.", contact.id)

    def add_tag(self, contact_id: str, tag: str) -> None:
        url = f"{GHL_BASE_URL}/contacts/{contact_id}/tags"
        resp = requests.post(
            url,
            json={"tags": [tag]},
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Tag '%s' added to contact %s.", tag, contact_id)

    def remove_tag(self, contact_id: str, tag: str) -> None:
        url = f"{GHL_BASE_URL}/contacts/{contact_id}/tags"
        resp = requests.delete(
            url,
            json={"tags": [tag]},
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Tag '%s' removed from contact %s.", tag, contact_id)

    # ------------------------------------------------------------------
    # Opportunities (pipeline)
    # ------------------------------------------------------------------

    def move_to_pipeline(
        self,
        contact: Contact,
        stage_id: str,
    ) -> str:
        """Create or update the opportunity for this contact; return opportunity ID."""
        payload = {
            "pipelineId": self._config.ghl_pipeline_id,
            "locationId": self._config.ghl_location_id,
            "name": f"{contact.display_name} — {contact.property_name or contact.display_location}",
            "contactId": contact.id,
            "stageId": stage_id,
            "status": "open",
        }
        url = f"{GHL_BASE_URL}/opportunities/"
        resp = requests.post(url, json=payload, headers=self._headers, timeout=15)
        resp.raise_for_status()
        opp_id = resp.json().get("opportunity", {}).get("id", "")
        logger.info(
            "Contact %s moved to pipeline stage %s (opportunity %s).",
            contact.id,
            stage_id,
            opp_id,
        )
        return opp_id

    def update_opportunity_stage(self, opportunity_id: str, stage_id: str) -> None:
        url = f"{GHL_BASE_URL}/opportunities/{opportunity_id}"
        resp = requests.put(
            url,
            json={"stageId": stage_id},
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Opportunity %s moved to stage %s.", opportunity_id, stage_id)

    # ------------------------------------------------------------------
    # Activity notes
    # ------------------------------------------------------------------

    def log_note(self, contact_id: str, note: str) -> None:
        url = f"{GHL_BASE_URL}/contacts/{contact_id}/notes"
        resp = requests.post(
            url,
            json={"body": note},
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Note logged for contact %s.", contact_id)

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def create_task(
        self,
        contact_id: str,
        title: str,
        due_date: datetime,
        assigned_to: str,
        high_priority: bool = False,
    ) -> str:
        payload = {
            "title": title,
            "dueDate": due_date.isoformat(),
            "assignedTo": assigned_to,
            "contactId": contact_id,
            "completed": False,
        }
        url = f"{GHL_BASE_URL}/contacts/{contact_id}/tasks"
        resp = requests.post(url, json=payload, headers=self._headers, timeout=15)
        resp.raise_for_status()
        task_id = resp.json().get("task", {}).get("id", "")
        logger.info(
            "Task '%s' created for contact %s (due %s)%s.",
            title,
            contact_id,
            due_date.date(),
            " [HIGH PRIORITY]" if high_priority else "",
        )
        return task_id

    def close_task(self, contact_id: str, task_id: str) -> None:
        url = f"{GHL_BASE_URL}/contacts/{contact_id}/tasks/{task_id}"
        resp = requests.put(
            url,
            json={"completed": True},
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Task %s closed.", task_id)


# ---------------------------------------------------------------------------
# High-level CRM actions (Step 5)
# ---------------------------------------------------------------------------


def post_send_crm_actions(
    contact: Contact,
    email_content: EmailContent,
    config: Config,
    sent_at: datetime | None = None,
) -> dict:
    """
    Execute all CRM actions immediately after the initial email is sent:
      1. Move contact to pipeline stage "Emailed — Awaiting Reply"
      2. Log activity note
      3. Create follow-up task (due 3 days from now)

    Returns a dict with opportunity_id and task_id for downstream use.
    """
    if sent_at is None:
        sent_at = datetime.now(timezone.utc)

    ghl = GHLClient(config)
    date_str = sent_at.strftime("%Y-%m-%d %H:%M UTC")

    opp_id = ghl.move_to_pipeline(contact, config.ghl_stage_emailed_id)

    note = (
        f"AI outreach email sent on {date_str}.\n"
        f"Segment: {contact.segment.value if contact.segment else 'unknown'}.\n"
        f"Pain angle used: {email_content.pain_point}"
    )
    ghl.log_note(contact.id, note)

    follow_up_due = sent_at + timedelta(days=3)
    property_label = f" ({contact.property_name})" if contact.property_name else ""
    task_title = f"Follow-up check — {contact.display_name}{property_label}"
    task_id = ghl.create_task(
        contact_id=contact.id,
        title=task_title,
        due_date=follow_up_due,
        assigned_to=config.ghl_user_id,
    )

    logger.info("Post-send CRM actions complete for contact %s.", contact.id)
    return {"opportunity_id": opp_id, "task_id": task_id}
