import uuid

from tortoise import fields
from tortoise.models import Model
from app.utils import generate_uuid, now

class User(Model):
    """
    Admin/user account for the AI Chatbot Portal.
    Passwords are stored as bcrypt hashes — never plaintext.
    """

    id = fields.UUIDField(primary_key=True, default=generate_uuid)
    email = fields.CharField(max_length=255, unique=True)
    display_name = fields.CharField(max_length=255, null=True)
    hashed_password = fields.CharField(max_length=500)
    role = fields.CharField(max_length=20, default="user")     # user | admin
    avatar_url = fields.CharField(max_length=500, null=True)
    is_active = fields.BooleanField(default=True)
    is_ephemeral = fields.BooleanField(default=False)  # anonymous temp-user; prune later

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"

    def __str__(self) -> str:
        return self.email

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

class UserAPIKey(Model):
    """
    API keys for users to access the AI Chatbot API.
    Each key is associated with a user and has its own permissions and expiration.
    """

    id = fields.UUIDField(primary_key=True, default=generate_uuid)
    user = fields.ForeignKeyField("models.User", related_name="api_keys")
    name = fields.CharField(max_length=255)
    key_hash = fields.CharField(max_length=64, unique=True, null=True)
    key_prefix = fields.CharField(max_length=16, default="")
    last_used_at = fields.DatetimeField(null=True)
    expires_at = fields.DatetimeField(null=True)       # null = never expires
    revoked_at = fields.DatetimeField(null=True)       # set when revoked; null = active
    created_at = fields.DatetimeField(auto_now_add=True)

    def is_usable(self) -> bool:
        """True when the key is neither revoked nor expired."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= now():
            return False
        return True

    class Meta:
        table = "user_api_keys"
