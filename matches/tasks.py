import logging
from io import StringIO

from celery import shared_task
from django.core.management import call_command


logger = logging.getLogger(__name__)


@shared_task(bind=True, name="matches.tasks.sync_live_matches")
def sync_live_matches(self):
    """Synchronize live/recent football-data.org matches from Celery Beat."""
    stdout = StringIO()
    stderr = StringIO()
    args = [
        "sync_football_data",
        "--live",
        "--days-back",
        "1",
        "--days-forward",
        "1",
        "--fetch-padding-days",
        "1",
        "--no-refresh-scorers",
    ]

    call_command(*args, stdout=stdout, stderr=stderr, verbosity=2)

    output = stdout.getvalue().strip()
    error_output = stderr.getvalue().strip()
    if output:
        logger.info("Celery live sync completed: %s", output)
    if error_output:
        logger.warning("Celery live sync stderr: %s", error_output)

    return {
        "task_id": self.request.id,
        "command": "python manage.py " + " ".join(args),
        "stdout": output,
        "stderr": error_output,
    }

