import json
import zoneinfo
from datetime import datetime

import croniter
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

import integrations

_COUNT_LABELS = (
    "TV Seasons",
    "TV Shows",
    "TV Season",
    "TV Show",
    "Episodes",
    "Episode",
    "Movies",
    "Movie",
    "Boardgames",
    "Boardgame",
    "Comics",
    "Comic",
    "Books",
    "Book",
    "Games",
    "Game",
    "Anime",
    "Manga",
)


def _translate_count_phrase(phrase):
    """Translate a stored fragment such as ``1481 Movies``."""
    count, _space, label = phrase.partition(" ")
    if not count.isdigit() or label not in _COUNT_LABELS:
        return phrase
    return _("%(count)s " + label) % {"count": count}


def _translate_import_items(text):
    """Translate the list inside a stored import summary."""
    if " and " not in text:
        return _translate_count_phrase(text)
    earlier, last = text.rsplit(" and ", 1)
    earlier_text = ", ".join(
        _translate_count_phrase(part.strip())
        for part in earlier.split(",")
        if part.strip()
    )
    return _("%(earlier)s and %(last)s") % {
        "earlier": earlier_text,
        "last": _translate_count_phrase(last.strip()),
    }


def translate_import_summary(summary):
    """Translate an import result that was stored in English."""
    if summary == "No media was imported.":
        return _("No media was imported.")
    prefix = "Imported "
    if summary.startswith(prefix) and summary.endswith("."):
        items = _translate_import_items(summary[len(prefix):-1])
        return _("Imported %(items)s.") % {"items": items}
    return summary


def process_task_result(task):
    """Process task result based on status and format appropriately."""
    if task.status == "FAILURE":
        result_json = json.loads(task.result)
        if result_json["exc_type"] == "MediaImportError":
            task.summary = result_json["exc_message"][0]
            task.errors = task.traceback
        else:
            task.summary = _("Unexpected error occurred while processing the task.")
            task.errors = task.traceback
    elif task.status == "STARTED":
        task.summary = _("This task is currently running.")
        task.errors = None
    elif task.status == "SUCCESS":
        result_json = json.loads(task.result)
        # Split by the error indicator
        parts = result_json.split(integrations.tasks.ERROR_TITLE.strip())
        if len(parts) > 1:
            # We have both summary and errors
            task.summary = translate_import_summary(parts[0].strip())

            # Keep errors as a single string with newlines
            task.errors = parts[1].strip()
        else:
            # Only summary, no errors
            task.summary = translate_import_summary(result_json.strip())
            task.errors = None
    elif task.status == "PENDING":
        task.summary = _("This task has been queued and is waiting to run.")
        task.errors = None

    return task


def _every_n_hours(step):
    """Return a translated label such as “Every 3 hours”."""
    count = int(step)
    return ngettext(
        "Every %(count)s hour",
        "Every %(count)s hours",
        count,
    ) % {"count": count}


def _hour_frequency_label(hour_field, day_of_week):
    """Return a label when the crontab repeats every 1, 3, 6, or 12 hours."""
    if day_of_week != "*":
        return None
    hour = str(hour_field)
    if hour in {"*", "*/1"}:
        return _("Every hour")
    if hour.startswith("*/"):
        step_text = hour[2:]
        if step_text in {"3", "6", "12"}:
            return _every_n_hours(step_text)
        return None
    if "," not in hour:
        return None
    try:
        hours = sorted({int(part) for part in hour.split(",") if part != ""})
    except ValueError:
        return None
    if len(hours) < 2:
        return None
    gaps = [(hours[(index + 1) % len(hours)] - hours[index]) % 24 for index in range(len(hours))]
    step = gaps[0]
    if len(set(gaps)) == 1 and step in {3, 6, 12} and len(hours) == 24 // step:
        return _every_n_hours(step)
    return None


def get_next_run_info(periodic_task):
    """Calculate next run time and frequency for a periodic task."""
    if not periodic_task.crontab:
        return None

    try:
        kwargs = json.loads(periodic_task.kwargs)
        mode = kwargs.get("mode", "new")  # Default to 'new' if not specified
    except json.JSONDecodeError:
        mode = "new"

    mode = _("Only New Items") if mode == "new" else _("Overwrite Existing")

    cron = periodic_task.crontab
    tz = zoneinfo.ZoneInfo(str(cron.timezone))
    now = timezone.now().astimezone(tz)

    # Create cron expression
    cron_expr = (
        f"{cron.minute} {cron.hour} {cron.day_of_month} "
        f"{cron.month_of_year} {cron.day_of_week}"
    )
    cron_iter = croniter.croniter(cron_expr, now)
    next_run = cron_iter.get_next(datetime)

    hour_frequency = _hour_frequency_label(cron.hour, cron.day_of_week)
    if hour_frequency:
        frequency = hour_frequency
    elif cron.day_of_week == "*":
        frequency = _("Every Day")
    elif cron.day_of_week == "*/2":
        frequency = _("Every 2 days")
    else:
        frequency = _("Cron: %(expression)s") % {"expression": cron_expr}

    return {
        "next_run": next_run,
        "frequency": frequency,
        "mode": mode,
    }
