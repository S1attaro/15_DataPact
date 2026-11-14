"""
Load AI request logs from a CSV into AIRequestLog (A10, Connor Slattery).

    python manage.py load_ai_logs                      # data/ai_logs.csv
    python manage.py load_ai_logs path/to/file.csv
    python manage.py load_ai_logs --keep-live          # keep rows from real use

By default every existing row is deleted first, so loading the same file
twice does not double the dashboard. --keep-live deletes only benchmark and
simulated rows and keeps what real users logged on this server.

The CSV is what collect_ai_logs writes: one row per request, with the
columns in CSV_FIELDS. cost_usd is read from the file, not worked out again.
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from data_quality.models import AIRequestLog

CSV_FIELDS = [
    "created_at", "feature", "engine", "model_name", "user_label", "query_type",
    "input_chars", "prompt_tokens", "completion_tokens", "retrieval_ms", "latency_ms",
    "status", "cost_usd", "source",
]
INT_FIELDS = ("input_chars", "prompt_tokens", "completion_tokens")
FLOAT_FIELDS = ("retrieval_ms", "latency_ms")
CHOICES = {
    "feature": AIRequestLog.Feature.values,
    "engine": AIRequestLog.Engine.values,
    "status": AIRequestLog.Status.values,
    "source": AIRequestLog.Source.values,
}


def parse_row(row, line):
    missing = [name for name in CSV_FIELDS if name not in row]
    if missing:
        raise CommandError(f"Line {line}: missing columns {', '.join(missing)}")
    fields = {}
    try:
        created = parse_datetime(row["created_at"])
        if created is None:
            raise ValueError("bad created_at")
        fields["created_at"] = created
        for name in INT_FIELDS:
            fields[name] = int(float(row[name] or 0))
        for name in FLOAT_FIELDS:
            fields[name] = float(row[name] or 0)
        fields["cost_usd"] = Decimal(row["cost_usd"] or "0")
    except (ValueError, InvalidOperation) as exc:
        raise CommandError(f"Line {line}: {exc}") from None
    for name, allowed in CHOICES.items():
        if row[name] not in allowed:
            raise CommandError(f"Line {line}: {name} must be one of {', '.join(allowed)}")
        fields[name] = row[name]
    fields["model_name"] = row["model_name"][:100]
    fields["user_label"] = row["user_label"][:40]
    fields["query_type"] = row["query_type"][:40]
    return AIRequestLog(**fields)


class Command(BaseCommand):
    help = "Load AI request logs from a CSV (default data/ai_logs.csv) for the analytics dashboard."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(Path(settings.BASE_DIR) / "data" / "ai_logs.csv"))
        parser.add_argument("--keep-live", action="store_true",
                            help="Keep rows logged by real use of this site; replace only the rest.")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"No such file: {path}")
        with path.open(newline="", encoding="utf-8") as handle:
            rows = [parse_row(row, number) for number, row in enumerate(csv.DictReader(handle), start=2)]
        with transaction.atomic():
            old = AIRequestLog.objects.all()
            if options["keep_live"]:
                old = old.exclude(source=AIRequestLog.Source.LIVE)
            deleted, _ = old.delete()
            AIRequestLog.objects.bulk_create(rows, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} AI requests from {path} (removed {deleted} old rows)."))
