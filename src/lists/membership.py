"""Batch helpers for “this title is on one of my custom lists” badges."""

from __future__ import annotations

from django.db.models import Q

from app.models import Item
from lists.models import CustomListItem


def item_ids_on_user_lists(user, item_ids) -> set[int]:
    """Return the subset of ``item_ids`` that appear on the user's lists."""
    if user is None:
        return set()
    membership = CustomListItem.objects.get_user_item_lists_map(user, item_ids)
    return {item_id for item_id, lists in membership.items() if lists}


def attach_on_list(user, objects) -> None:
    """Set ``on_list`` on media rows / Item instances (and nested ``.item``)."""
    if user is None or not objects:
        return

    item_ids = []
    for obj in objects:
        item = _extract_item(obj)
        item_id = getattr(item, "id", None) if item is not None else None
        if item_id is not None:
            item_ids.append(item_id)

    on_list_ids = item_ids_on_user_lists(user, item_ids)
    for obj in objects:
        item = _extract_item(obj)
        item_id = getattr(item, "id", None) if item is not None else None
        flag = item_id in on_list_ids
        try:
            obj.on_list = flag
        except Exception:
            pass
        if item is not None:
            try:
                item.on_list = flag
            except Exception:
                pass


def attach_on_list_to_enriched(user, enriched_items) -> None:
    """Set ``on_list`` on enriched search/recommendation rows."""
    if user is None or not enriched_items:
        return

    medias = [row["media"] for row in enriched_items if row.get("media") is not None]
    attach_on_list(user, medias)

    missing = [row for row in enriched_items if row.get("media") is None]
    by_key = {}
    if missing:
        query = Q()
        for row in missing:
            item = row.get("item") or {}
            filters = Q(
                media_id=str(item.get("media_id")),
                source=item.get("source"),
                media_type=item.get("media_type"),
            )
            season_number = item.get("season_number")
            episode_number = item.get("episode_number")
            filters &= (
                Q(season_number=season_number)
                if season_number is not None
                else Q(season_number__isnull=True)
            )
            filters &= (
                Q(episode_number=episode_number)
                if episode_number is not None
                else Q(episode_number__isnull=True)
            )
            query |= filters

        items = list(
            Item.objects.filter(query).only(
                "id",
                "media_id",
                "source",
                "media_type",
                "season_number",
                "episode_number",
            )
        )
        by_key = {
            (
                str(item.media_id),
                item.source,
                item.media_type,
                item.season_number,
                item.episode_number,
            ): item.id
            for item in items
        }

    on_list_ids = item_ids_on_user_lists(user, list(by_key.values()))

    for row in enriched_items:
        media = row.get("media")
        if media is not None:
            flag = bool(getattr(media, "on_list", False))
        else:
            item = row.get("item") or {}
            key = (
                str(item.get("media_id")),
                item.get("source"),
                item.get("media_type"),
                item.get("season_number"),
                item.get("episode_number"),
            )
            flag = by_key.get(key) in on_list_ids
        _set_item_flag(row.get("item"), flag)
        row["on_list"] = flag


def item_on_user_lists(user, item) -> bool:
    """Return True when a single Item is on any of the user's custom lists."""
    if user is None or item is None or not getattr(item, "id", None):
        return False
    return item.id in item_ids_on_user_lists(user, [item.id])


def _extract_item(obj):
    if isinstance(obj, Item):
        return obj
    return getattr(obj, "item", None)


def _set_item_flag(item, flag: bool) -> None:
    if item is None:
        return
    if isinstance(item, dict):
        item["on_list"] = flag
        return
    try:
        item.on_list = flag
    except Exception:
        pass
