"""Tests for custom-list membership badges."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import Item, MediaTypes, Sources
from lists.membership import attach_on_list, attach_on_list_to_enriched, item_on_user_lists
from lists.models import CustomList, CustomListItem

User = get_user_model()


class ListMembershipTests(TestCase):
    """on_list flags for cards and detail pages."""

    def setUp(self):
        self.user = User.objects.create_user(username="listbadge", password="pass")
        self.item = Item.objects.create(
            media_id="60800",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Cat City",
            image="http://example.com/poster.jpg",
        )
        self.other = Item.objects.create(
            media_id="11",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Other",
            image="http://example.com/other.jpg",
        )
        self.custom_list = CustomList.objects.create(
            owner=self.user,
            name="Watch later",
        )
        CustomListItem.objects.create(custom_list=self.custom_list, item=self.item)

    def test_item_on_user_lists(self):
        self.assertTrue(item_on_user_lists(self.user, self.item))
        self.assertFalse(item_on_user_lists(self.user, self.other))

    def test_attach_on_list(self):
        attach_on_list(self.user, [self.item, self.other])
        self.assertTrue(self.item.on_list)
        self.assertFalse(self.other.on_list)

    def test_attach_on_list_to_enriched_dicts(self):
        rows = [
            {
                "item": {
                    "media_id": "60800",
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "title": "Cat City",
                    "image": "x",
                },
                "media": None,
            },
            {
                "item": {
                    "media_id": "11",
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "title": "Other",
                    "image": "y",
                },
                "media": None,
            },
        ]
        attach_on_list_to_enriched(self.user, rows)
        self.assertTrue(rows[0]["on_list"])
        self.assertTrue(rows[0]["item"]["on_list"])
        self.assertFalse(rows[1]["on_list"])
