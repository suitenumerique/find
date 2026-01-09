"""
Built-in self-tests for core system components.

This module contains self-tests for database, cache, and OpenSearch connectivity.
"""

import time

from django.conf import settings
from django.core.cache import cache
from django.db import connection

from .selftests import SelfTest, SelfTestResult, registry
from .services.opensearch import opensearch_client


class DatabaseSelfTest(SelfTest):
    """Test database connectivity."""

    name = "Database Connection"
    description = "Verify that the database is accessible and responsive"

    def run(self) -> SelfTestResult:
        """Test database connection by executing a simple query."""
        start_time = time.time()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            duration_ms = (time.time() - start_time) * 1000

            if result and result[0] == 1:
                return SelfTestResult(
                    name=self.name,
                    success=True,
                    message="Database connection successful",
                    details={
                        "database": settings.DATABASES["default"]["NAME"],
                        "engine": settings.DATABASES["default"]["ENGINE"],
                    },
                    duration_ms=duration_ms,
                )
            return SelfTestResult(
                name=self.name,
                success=False,
                message="Database query returned unexpected result",
                duration_ms=duration_ms,
            )
        except (OSError, ValueError) as e:
            duration_ms = (time.time() - start_time) * 1000
            return SelfTestResult(
                name=self.name,
                success=False,
                message=f"Database connection failed: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration_ms,
            )


class CacheSelfTest(SelfTest):
    """Test cache (Redis) connectivity."""

    name = "Cache Connection"
    description = "Verify that the cache system is accessible and functional"

    def run(self) -> SelfTestResult:
        """Test cache by setting and getting a test value."""
        start_time = time.time()
        test_key = "selftest:cache:ping"
        test_value = "pong"

        try:
            # Try to set a value
            cache.set(test_key, test_value, timeout=10)

            # Try to get the value back
            retrieved_value = cache.get(test_key)

            # Clean up
            cache.delete(test_key)

            duration_ms = (time.time() - start_time) * 1000

            if retrieved_value == test_value:
                cache_backend = settings.CACHES.get("default", {}).get(
                    "BACKEND", "unknown"
                )
                return SelfTestResult(
                    name=self.name,
                    success=True,
                    message="Cache connection successful",
                    details={"backend": cache_backend},
                    duration_ms=duration_ms,
                )
            return SelfTestResult(
                name=self.name,
                success=False,
                message="Cache value mismatch",
                details={
                    "expected": test_value,
                    "received": retrieved_value,
                },
                duration_ms=duration_ms,
            )
        except (OSError, ValueError, TimeoutError) as e:
            duration_ms = (time.time() - start_time) * 1000
            return SelfTestResult(
                name=self.name,
                success=False,
                message=f"Cache connection failed: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration_ms,
            )


class OpenSearchSelfTest(SelfTest):
    """Test OpenSearch connectivity."""

    name = "OpenSearch Connection"
    description = "Verify that OpenSearch is accessible and responsive"

    def run(self) -> SelfTestResult:
        """Test OpenSearch connection by checking cluster health."""
        start_time = time.time()
        try:
            client = opensearch_client()

            # Ping the cluster
            if not client.ping():
                duration_ms = (time.time() - start_time) * 1000
                return SelfTestResult(
                    name=self.name,
                    success=False,
                    message="OpenSearch ping failed",
                    duration_ms=duration_ms,
                )

            # Get cluster health
            health = client.cluster.health()

            duration_ms = (time.time() - start_time) * 1000

            return SelfTestResult(
                name=self.name,
                success=True,
                message="OpenSearch connection successful",
                details={
                    "cluster_name": health.get("cluster_name", "unknown"),
                    "status": health.get("status", "unknown"),
                    "number_of_nodes": health.get("number_of_nodes", 0),
                    "number_of_data_nodes": health.get("number_of_data_nodes", 0),
                    "active_shards": health.get("active_shards", 0),
                    "host": settings.OPENSEARCH_HOST,
                    "port": settings.OPENSEARCH_PORT,
                },
                duration_ms=duration_ms,
            )
        except (OSError, ValueError, TimeoutError) as e:
            duration_ms = (time.time() - start_time) * 1000
            return SelfTestResult(
                name=self.name,
                success=False,
                message=f"OpenSearch connection failed: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration_ms,
            )


# Register all built-in tests
registry.register(DatabaseSelfTest)
registry.register(CacheSelfTest)
registry.register(OpenSearchSelfTest)
