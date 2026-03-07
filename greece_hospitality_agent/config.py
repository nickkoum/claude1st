"""Configuration loaded from environment variables."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    # Anthropic
    anthropic_api_key: str

    # Sender identity
    sender_email: str
    sender_display_name: str      # e.g. "Nikos from YourCompany"
    sender_first_name: str        # e.g. "Nikos"

    # GoHighLevel CRM
    ghl_api_key: str
    ghl_location_id: str
    ghl_user_id: str              # Assigned-to user for tasks
    ghl_pipeline_id: str          # "Greece Hospitality Outreach" pipeline ID
    ghl_stage_emailed_id: str     # Stage: "Emailed — Awaiting Reply"
    ghl_stage_replied_id: str     # Stage: "Replied — Needs Human"
    ghl_stage_complete_id: str    # Stage: "Sequence Complete — No Reply"

    # Internal notifications
    notification_email: str       # Where to send "new reply" alerts

    # SMTP (for sending outreach emails)
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool = True


def load_config() -> Config:
    """Load config from environment variables. Raises if required vars are missing."""

    def require(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise EnvironmentError(f"Required environment variable '{name}' is not set.")
        return value

    def optional(name: str, default: str = "") -> str:
        return os.environ.get(name, default)

    return Config(
        anthropic_api_key=require("ANTHROPIC_API_KEY"),
        sender_email=require("SENDER_EMAIL"),
        sender_display_name=require("SENDER_DISPLAY_NAME"),
        sender_first_name=require("SENDER_FIRST_NAME"),
        ghl_api_key=require("GHL_API_KEY"),
        ghl_location_id=require("GHL_LOCATION_ID"),
        ghl_user_id=require("GHL_USER_ID"),
        ghl_pipeline_id=require("GHL_PIPELINE_ID"),
        ghl_stage_emailed_id=require("GHL_STAGE_EMAILED_ID"),
        ghl_stage_replied_id=require("GHL_STAGE_REPLIED_ID"),
        ghl_stage_complete_id=require("GHL_STAGE_COMPLETE_ID"),
        notification_email=require("NOTIFICATION_EMAIL"),
        smtp_host=require("SMTP_HOST"),
        smtp_port=int(optional("SMTP_PORT", "587")),
        smtp_username=require("SMTP_USERNAME"),
        smtp_password=require("SMTP_PASSWORD"),
        smtp_use_tls=optional("SMTP_USE_TLS", "true").lower() == "true",
    )
