"""Factories for the find's core app"""

from uuid import uuid4

from django.utils import timezone
from django.utils.text import slugify

import factory
from faker import Faker

from . import enums, models

fake = Faker()


class DocumentSchemaFactory(factory.DictFactory):
    """
    A factory for generating dictionaries that represent a document for
    indexation for testing and development purposes.
    """

    id = factory.LazyFunction(lambda: str(uuid4()))
    title = factory.Sequence(lambda n: f"Test title {n!s}")
    path = factory.Sequence(lambda n: f"000{n}")
    content = factory.Sequence(lambda n: f"Test content {n!s}")
    created_at = factory.LazyFunction(
        lambda: fake.date_time_this_decade(tzinfo=timezone.get_current_timezone())
    )
    size = factory.LazyFunction(lambda: fake.random_int(min=0, max=1024**2))
    users = factory.LazyFunction(lambda: [str(uuid4()) for _ in range(3)])
    groups = factory.LazyFunction(lambda: [slugify(fake.word()) for _ in range(3)])
    reach = factory.Iterator(list(enums.ReachEnum))
    depth = 1
    numchild = 0
    is_active = True

    @factory.lazy_attribute
    def updated_at(self):
        """Ensure updated_at is after created_at and before now"""
        return fake.date_time_between(
            start_date=self.created_at,
            end_date=timezone.now(),
            tzinfo=timezone.get_current_timezone(),
        )


class ServiceFactory(factory.django.DjangoModelFactory):
    """
    A factory for generating service instances for testing and development purposes.
    """

    name = factory.Sequence(lambda n: f"test-index-{n!s}")
    created_at = factory.Faker("date_time_this_year", tzinfo=None)
    is_active = True
    client_id = "some_client_id"

    class Meta:
        model = models.Service


class IndexDocumentFactory(factory.DictFactory):
    """
    A factory for generating dictionaries that represent a document for
    indexation for testing and development purposes.
    """

    id = factory.LazyFunction(lambda: str(uuid4()))
    title = factory.Sequence(lambda n: f"Test title {n!s}")
    path = factory.Sequence(lambda n: f"000{n}")
    content = factory.Sequence(lambda n: f"Test content {n!s}")
    content_status = enums.ContentStatusEnum.READY
    content_uri = ""
    created_at = factory.LazyFunction(
        lambda: fake.date_time_this_decade(tzinfo=timezone.get_current_timezone())
    )
    size = factory.LazyFunction(lambda: fake.random_int(min=0, max=1024**2))
    users = factory.LazyFunction(lambda: [str(uuid4()) for _ in range(3)])
    groups = factory.LazyFunction(lambda: [slugify(fake.word()) for _ in range(3)])
    reach = factory.Iterator(list(enums.ReachEnum))
    depth = 1
    numchild = 0
    is_active = True

    class Meta:
        """Factory model"""

        model = models.IndexDocument

    @factory.lazy_attribute
    def updated_at(self):
        """Ensure updated_at is after created_at and before now"""
        return fake.date_time_between(
            start_date=self.created_at,
            end_date=timezone.now(),
            tzinfo=timezone.get_current_timezone(),
        )
