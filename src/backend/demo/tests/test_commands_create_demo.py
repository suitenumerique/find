"""Test the `create_demo` management command"""

from unittest import mock

from django.core.management import call_command
from django.test import override_settings

import pytest

from core import models
from core.services import opensearch
from demo import defaults

pytestmark = pytest.mark.django_db

TEST_NB_OBJECTS = {
    "documents": 4,
    "services": 2,
}


@override_settings(DEBUG=True)
@mock.patch.dict(defaults.NB_OBJECTS, TEST_NB_OBJECTS)
def test_commands_create_demo():
    """The create_demo management command should create objects as expected."""
    call_command("create_demo")

    assert models.Service.objects.exclude(name="docs").count() == 2
    assert opensearch.client.count()["count"] == 4

    docs = models.Service.objects.get(name="docs")
    assert docs.client_id == "impress"
