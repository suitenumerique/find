"""Custom django-configurations values for service configuration."""

import os
from collections import defaultdict

from django.utils.text import slugify

from configurations.values import Value


class ServicesValue(Value):
    """Auto-discover service configurations from SERVICES__*__* env vars.

    Scans environment variables for the pattern SERVICES__<NAME>__<FIELD>
    where FIELD is either TOKEN or CLIENT_ID. Groups them by service name
    and constructs ServiceConfig instances.

    Example:
        SERVICES__DOCS__TOKEN=find-api-key-for-docs
        SERVICES__DOCS__CLIENT_ID=00000000-0000-0000-0000-000000000001
        SERVICES__DRIVE__TOKEN=find-api-key-for-drive
        SERVICES__DRIVE__CLIENT_ID=00000000-0000-0000-0000-000000000002

        Returns: ServicesConfig with 2 services: "docs" and "drive"
    """

    def __init__(self, *args, **kwargs):
        """Initialize without reading from a specific env var."""
        # Don't read from a specific env var - we scan all of them
        kwargs.setdefault("environ", False)
        # Set a truthy default so __new__ calls setup()
        kwargs.setdefault("default", {})
        super().__init__(*args, **kwargs)

    def setup(self, name):
        """Override to always call to_python() regardless of environ setting."""
        self.value = self.to_python(self.default)
        return self.value

    def to_python(self, value):
        """Scan environment for SERVICES__<NAME>__<FIELD> patterns.

        Returns:
            ServicesConfig: Container with discovered service configurations.

        Raises:
            ValidationError: If a service is missing required fields (token or client_id).
        """
        # Lazy import to avoid circular import during settings load
        from core.services.config import ServiceConfig, ServicesConfig  # noqa: PLC0415

        # Group env vars by service name
        services_data = defaultdict(dict)

        for key, val in os.environ.items():
            if not key.startswith("SERVICES__"):
                continue

            parts = key.split("__")
            if len(parts) != 3:
                continue  # Skip malformed keys

            _, service_name, field = parts
            field_lower = field.lower()

            if field_lower in ("token", "client_id"):
                services_data[service_name][field_lower] = val

        # Build ServiceConfig instances
        service_configs = []
        for name, data in services_data.items():
            config = ServiceConfig(
                name=name,
                token=data.get("token", ""),
                client_id=data.get("client_id", ""),
            )
            service_configs.append(config)

        return ServicesConfig(service=service_configs)
