"""Opaque server-side session store: session id -> user, with expiry."""
from tortoise import fields
from tortoise.models import Model


class Session(Model):
    id = fields.CharField(max_length=64, primary_key=True)  # generate_uuid7().hex
    user = fields.ForeignKeyField("models.User", related_name="sessions", null=True)
    expires_at = fields.DatetimeField(db_index=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "sessions"
