import uuid

from tortoise import fields
from tortoise.models import Model
from app.utils import generate_uuid

class Conversation(Model):
    """
    Chat conversation — mirrors the `conversations` table from the original Supabase schema.
    """

    id = fields.UUIDField(primary_key=True, default=generate_uuid)
    title = fields.CharField(max_length=500, default="สนทนาใหม่")
    preview = fields.TextField(null=True)
    agencies = fields.JSONField(default=list)          # list[str] — agency names used
    status = fields.CharField(max_length=20, default="success")   # success | failed
    message_count = fields.IntField(default=0)
    response_time = fields.CharField(max_length=50, null=True)
    external_session_id = fields.CharField(max_length=100, null=True) # for tracking sessions with external APIs
    metadata = fields.JSONField(default=dict)           # arbitrary provider-specific metadata
    deleted_at = fields.DatetimeField(null=True)        # soft-delete marker; null = not deleted

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    user = fields.ForeignKeyField(
        "models.User",
        related_name="conversations",
        on_delete=fields.SET_NULL,
        null=True,
    )

    class Meta:
        table = "conversations"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class Message(Model):
    """
    Individual chat message within a conversation.
    """

    id = fields.UUIDField(primary_key=True, default=generate_uuid)
    parent_id = fields.UUIDField(null=True)  # for threading or follow-up messages
    conversation = fields.ForeignKeyField(
        "models.Conversation",
        related_name="messages",
        on_delete=fields.CASCADE,
    )
    role = fields.CharField(max_length=20)              # user | assistant
    content = fields.TextField()
    agent_steps = fields.JSONField(default=list)        # list of AgentStep objects
    sources = fields.JSONField(default=list)            # list of source references
    summary = fields.TextField(null=True)               # v5 executive summary (LLM-written); None in v4 mode
    summary_references = fields.JSONField(default=list) # v5 references[] — scoped to `summary` only
    rating = fields.CharField(max_length=10, null=True) # up | down | None
    feedback_text = fields.TextField(null=True)
    response_time = fields.IntField(null=True)        # in seconds
    category = fields.CharField(max_length=50, null=True) # สอบถามข้อมูล | ตรวจสอบสถานะ | ขั้นตอนดำเนินการ | กฎหมาย/ระเบียบ
    agency_ids = fields.JSONField(default=list, null=True)     # list of agency ids involved in this message
    errors = fields.JSONField(default=list, null=True)       # list of error messages if any
    deleted_at = fields.DatetimeField(null=True)        # soft-delete marker; null = not deleted

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    user = fields.ForeignKeyField(
        "models.User",
        related_name="messages",
        on_delete=fields.SET_NULL,
        null=True,
    )

    class Meta:
        table = "messages"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"[{self.role}] {self.content[:60]}"