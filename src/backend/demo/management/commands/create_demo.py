# ruff: noqa: S311, S106
"""create_demo management command"""

import logging
import random
import time
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify

from faker import Faker
from opensearchpy.helpers import bulk

from core import factories, opensearch

from demo import defaults

fake = Faker()

logger = logging.getLogger("find.commands.demo.create_demo")


class BulkIndexing:
    """A utility class to index to OpenSearch in bulk by just pushing to a queue."""

    BATCH_SIZE = 20000

    def __init__(self, stdout, *args, **kwargs):
        """Define actions as a list."""
        self.actions = []
        self.stdout = stdout
        self.logger = logging.getLogger(__name__)

    def bulk_index(self):
        """Actually index documents in bulk to OpenSearch."""
        _success, failed = bulk(opensearch.client, self.actions, stats_only=False)

        if failed:
            self.handle_failures(failed)

        # Clear the actions list after bulk indexing and display progress
        self.actions.clear()
        self.stdout.write(".", ending="")

    def handle_failures(self, failed):
        """Handle the failed bulk operations."""
        for failure in failed:
            self.logger.error("Failed to index document: %s", failure)

    def push(self, index_name, _id, document):
        """Add a document to queue so that it gets created in bulk."""
        self.actions.append(
            {
                "_op_type": "index",
                "_index": index_name,
                "_id": _id,
                "_source": document,
            }
        )

        if len(self.actions) >= self.BATCH_SIZE:
            self.bulk_index()

    def flush(self):
        """Flush any remaining documents in the queue."""
        if self.actions:
            self.bulk_index()

    def __del__(self):
        """Ensure that any remaining documents are indexed when the instance is deleted."""
        self.flush()


class Timeit:
    """A utility context manager/method decorator to time execution."""

    total_time = 0

    def __init__(self, stdout, sentence=None):
        """Set the sentence to be displayed for timing information."""
        self.sentence = sentence
        self.start = None
        self.stdout = stdout

    def __call__(self, func):
        """Behavior on call for use as a method decorator."""

        def timeit_wrapper(*args, **kwargs):
            """wrapper to trigger/stop the timer before/after function call."""
            self.__enter__()
            result = func(*args, **kwargs)
            self.__exit__(None, None, None)
            return result

        return timeit_wrapper

    def __enter__(self):
        """Start timer upon entering context manager."""
        self.start = time.perf_counter()
        if self.sentence:
            self.stdout.write(self.sentence, ending=".")

    def __exit__(self, exc_type, exc_value, exc_tb):
        """Stop timer and display result upon leaving context manager."""
        if exc_type is not None:
            raise exc_type(exc_value)
        end = time.perf_counter()
        elapsed_time = end - self.start
        if self.sentence:
            self.stdout.write(f" Took {elapsed_time:g} seconds")

        self.__class__.total_time += elapsed_time
        return elapsed_time


def generate_document():
    """Generate a realistic document dictionary faster than factory_boy does it."""
    created_at = fake.past_datetime(tzinfo=timezone.get_current_timezone())
    updated_at = fake.date_time_between(
        start_date=created_at,
        end_date=timezone.now(),
        tzinfo=timezone.get_current_timezone(),
    )

    return {
        "title": fake.sentence(nb_words=10, variable_nb_words=True),
        "content": "\n".join(fake.paragraphs(nb=5)),
        "created_at": created_at,
        "updated_at": updated_at,
        "size": random.randint(0, 100 * 1024**2),
        "users": [str(uuid4()) for _ in range(3)],
        "groups": [slugify(fake.word()) for _ in range(3)],
        "is_public": fake.boolean(),
    }


def create_demo(stdout):
    """
    Create a database with demo data for developers to work in a realistic environment.
    """
    opensearch.client.indices.delete("*")

    with Timeit(stdout, "Creating services"):
        services = factories.ServiceFactory.create_batch(
            defaults.NB_OBJECTS["services"]
        )
        for service in services:
            opensearch.ensure_index_exists(service.index_name)
            opensearch.client.indices.refresh(index=service.index_name)

    with Timeit(stdout, "Creating documents"):
        actions = BulkIndexing(stdout)
        for _ in range(defaults.NB_OBJECTS["documents"]):
            service = random.choice(services)
            document = generate_document()
            actions.push(service.index_name, uuid4(), document)
        actions.flush()

    # Check and report on indexed documents
    total_indexed = 0
    for service in services:
        opensearch.client.indices.refresh(index=service.index_name)
        indexed = opensearch.client.count(index=service.index_name)["count"]
        stdout.write(f"  - {service.index_name:s}: {indexed:d} documents")
        total_indexed += indexed

    stdout.write(f"  TOTAL: {total_indexed:d} documents")


class Command(BaseCommand):
    """A management command to create a demo database."""

    help = __doc__

    def add_arguments(self, parser):
        """Add argument to require forcing execution when not in debug mode."""
        parser.add_argument(
            "-f",
            "--force",
            action="store_true",
            default=False,
            help="Force command execution despite DEBUG is set to False",
        )

    def handle(self, *args, **options):
        """Handling of the management command."""
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                (
                    "This command is not meant to be used in production environment "
                    "except you know what you are doing, if so use --force parameter"
                )
            )

        create_demo(self.stdout)
