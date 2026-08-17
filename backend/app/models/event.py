"""Domain-event outbox — the durable channel of the event-driven core.

A producer appends a row here (in its own DB transaction); a background
dispatcher later delivers undispatched rows to in-process consumers and stamps
`dispatched_at`. This decouples producers from consumers.
"""
from tortoise import fields
from tortoise.models import Model

from app.utils import generate_uuid


class DomainEvent(Model):
    id = fields.UUIDField(primary_key=True, default=generate_uuid)
    event_type = fields.CharField(max_length=100)
    payload = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)
    dispatched_at = fields.DatetimeField(null=True)

    class Meta:
        table = "domain_events"
        ordering = ["created_at"]
