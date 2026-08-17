"""Fixed-window rate-limit counter: one row per (key, window_start)."""
from tortoise import fields
from tortoise.models import Model


class RateLimitCounter(Model):
    id = fields.BigIntField(primary_key=True)
    key = fields.CharField(max_length=128)
    window_start = fields.BigIntField()          # epoch microseconds, window-floored
    count = fields.IntField(default=0)

    class Meta:
        table = "rate_limit_counters"
        unique_together = (("key", "window_start"),)
