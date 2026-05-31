"""Tests for authentication module"""

import logging
from unittest.mock import patch

import pytest

from core.authentication import FinderResourceServerBackend

pytestmark = pytest.mark.django_db


def test_resource_server_backend_init_failure_logs_exception(caplog):
    """Test that OIDC backend init failure logs exception with proper message"""
    with caplog.at_level(logging.ERROR, logger="core.authentication"):
        with patch("core.authentication.ResourceServerBackend.__init__") as mock_init:
            mock_init.side_effect = Exception("client_id=SECRET token=abc123")

            with pytest.raises(Exception):  # noqa: B017
                FinderResourceServerBackend()

        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        msg_list = [r.message for r in error_records]
        assert len(error_records) == 1, (
            f"Expected exactly 1 ERROR record, got {len(error_records)}: {msg_list}"
        )

        assert (
            error_records[0].message
            == "Failed to initialize OIDC resource server backend"
        ), f"Wrong message: {error_records[0].message!r}"
        assert "client_id=SECRET" not in error_records[0].message
        assert "token=abc123" not in error_records[0].message
        assert error_records[0].exc_info is not None
