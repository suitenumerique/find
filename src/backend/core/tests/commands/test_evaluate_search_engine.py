"""
Unit test for `reindex_with_embedding` command.
"""

from django.core.management import call_command

SERVICE_NAME = "test-index"


def test_evaluate():
    """Test evaluate"""
    call_command("evaluate_search_engine")
