from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("lists", "0004_customlistitem_list_item_id_and_more"),
        ("integrations", "0007_daily_nuvio_watch_history_reconcile"),
    ]

    operations = [
        migrations.AddField(
            model_name="nuvioaccount",
            name="library_cursor",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nuvioaccount",
            name="library_bootstrapped",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="nuvioaccount",
            name="watchlist_list",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="nuvio_watchlist_accounts",
                to="lists.customlist",
            ),
        ),
    ]
