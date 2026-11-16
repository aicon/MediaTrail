"""Durable SQLite-backed cache for IMDb / AI recommendation payloads."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

CACHE_TTL_DAYS = 30
SHARED_USER_ID = 0


def get_cached_payload(source: str, media_type: str, seed_key: str, user_id: int = SHARED_USER_ID):
    """Return fresh cached JSON payload, or None when missing/expired."""
    from app.models import RecommendationSourceCache

    row = (
        RecommendationSourceCache.objects.filter(
            source=source,
            media_type=media_type,
            seed_key=str(seed_key),
            user_id=user_id or SHARED_USER_ID,
            expires_at__gt=timezone.now(),
        )
        .only("payload")
        .first()
    )
    if row is None:
        return None
    return row.payload


def set_cached_payload(
    source: str,
    media_type: str,
    seed_key: str,
    payload,
    *,
    user_id: int = SHARED_USER_ID,
    ttl_days: int = CACHE_TTL_DAYS,
):
    """Upsert a recommendation payload with a durable expiry."""
    from app.models import RecommendationSourceCache

    now = timezone.now()
    RecommendationSourceCache.objects.update_or_create(
        source=source,
        media_type=media_type,
        seed_key=str(seed_key),
        user_id=user_id or SHARED_USER_ID,
        defaults={
            "payload": payload,
            "fetched_at": now,
            "expires_at": now + timedelta(days=ttl_days),
        },
    )
