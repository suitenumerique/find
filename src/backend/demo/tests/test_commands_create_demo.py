"""Test the `create_demo` management command"""

from unittest import mock

from django.core.management import call_command
from django.test import override_settings

import pytest

from core.services.opensearch import opensearch_client

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

    # Service model no longer exists, just verify indices were created
    # and documents were indexed
    assert opensearch_client().count()["count"] == 4

    # Verify that the dev service indices exist
    indices = opensearch_client().indices.get_alias(index="*")
    assert "docs" in indices
    assert "drive" in indices
    assert "conversations" in indices
