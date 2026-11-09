from django.conf import settings
from django.db import models


class NuvioAccount(models.Model):
    """Encrypted Nuvio sign-in and the per-user watch-history cursor."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="nuvio_account",
    )
    email = models.TextField()
    password = models.TextField()
    profile_id = models.PositiveIntegerField(default=1)
    cursor = models.BigIntegerField(null=True, blank=True)
    bootstrapped = models.BooleanField(default=False)
    imported_ids = models.JSONField(default=list)
    permanent_ids = models.JSONField(default=list)
    imdb_map = models.JSONField(default=dict)

    def __str__(self):
        """Return the owning user."""
        return f"Nuvio account for {self.user}"
