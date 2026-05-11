# ruff: noqa: S311
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

from core import enums, factories
from core.services.indexing import ensure_index_exists, prepare_document_for_indexing
from core.services.opensearch import opensearch_client

from demo import defaults

fake = Faker()

logger = logging.getLogger("find.commands.demo.create_demo")


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
        "title.en": fake.sentence(nb_words=10, variable_nb_words=True),
        "content.en": "\n".join(fake.paragraphs(nb=5)),
        "created_at": created_at,
        "updated_at": updated_at,
        "size": random.randint(0, 100 * 1024**2),
        "users": [str(uuid4()) for _ in range(3)],
        "groups": [slugify(fake.word()) for _ in range(3)],
        "reach": random.choice(list(enums.ReachEnum)).value,
    }


def create_demo(stdout):
    """
    Create a database with demo data for developers to work in a realistic environment.
    """
    opensearch_client_ = opensearch_client()
    opensearch_client_.indices.delete(index="*")

    with Timeit(stdout, "Creating services"):
        services = factories.ServiceFactory.create_batch(
            defaults.NB_OBJECTS["services"]
        )

        for service in services:
            ensure_index_exists(service.name)
            opensearch_client_.indices.refresh(index=service.name)

    with Timeit(stdout, "Creating documents"):
        for i in range(defaults.NB_OBJECTS["documents"]):
            service = random.choice(services)
            document = generate_document()
            doc_id = str(uuid4())

            raw_document = {
                "id": doc_id,
                "title": document.get("title.en", ""),
                "content": document.get("content.en", ""),
                "depth": 0,
                "path": "/",
                "numchild": 0,
                "created_at": document["created_at"],
                "updated_at": document["updated_at"],
                "size": document["size"],
                "users": document["users"],
                "groups": document["groups"],
                "reach": document["reach"],
                "is_active": True,
            }

            prepared = prepare_document_for_indexing(raw_document)
            prepared.pop("id")
            opensearch_client_.index(index=service.index_name, body=prepared, id=doc_id)

            if (i + 1) % 100 == 0:
                stdout.write(f"  Indexed {i + 1} documents...")

    with Timeit(stdout, "Creating dev services"):
        for conf in defaults.DEV_SERVICES:
            service = factories.ServiceFactory(**conf)
            ensure_index_exists(service.name)
            opensearch_client_.indices.refresh(index=service.name)

    # Check and report on indexed documents
    total_indexed = 0
    for service in services:
        opensearch_client_.indices.refresh(index=service.name)
        indexed = opensearch_client_.count(index=service.name)["count"]
        stdout.write(f"  - {service.name:s}: {indexed:d} documents")
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
