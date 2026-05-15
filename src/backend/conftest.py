import os

import configurations

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "find.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "Test")

os.environ.setdefault("OPENSEARCH_PASSWORD", "test-password")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-for-testing-only")

configurations.setup()
