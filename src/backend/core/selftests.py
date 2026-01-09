"""
Selftest registry and base classes for system health checks.

This module provides a modular system for registering and running self-tests
that check the health of various system components.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SelfTestResult:
    """Result of a self-test execution."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        name: str,
        success: bool,
        message: str,
        details: Optional[Dict] = None,
        duration_ms: Optional[float] = None,
    ):
        self.name = name
        self.success = success
        self.message = message
        self.details = details or {}
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict:
        """Convert result to dictionary."""
        return {
            "name": self.name,
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }


class SelfTest:
    """Base class for self-tests."""

    name: str = "Base Self Test"
    description: str = "Base self-test class"

    def run(self) -> SelfTestResult:
        """
        Execute the self-test.

        Returns:
            SelfTestResult: The result of the test execution.
        """
        raise NotImplementedError("Subclasses must implement the run method")


class SelfTestRegistry:
    """Registry for managing self-tests."""

    def __init__(self):
        self._tests: Dict[str, SelfTest] = {}

    def register(self, test_class: type[SelfTest]) -> None:
        """
        Register a self-test class.

        Args:
            test_class: The SelfTest subclass to register.
        """
        test_instance = test_class()
        test_id = test_class.__name__
        if test_id in self._tests:
            logger.warning("Self-test %s is already registered. Overwriting.", test_id)
        self._tests[test_id] = test_instance
        logger.debug("Registered self-test: %s - %s", test_id, test_instance.name)

    def unregister(self, test_class: type[SelfTest]) -> None:
        """
        Unregister a self-test class.

        Args:
            test_class: The SelfTest subclass to unregister.
        """
        test_id = test_class.__name__
        if test_id in self._tests:
            del self._tests[test_id]
            logger.debug("Unregistered self-test: %s", test_id)

    def get_all_tests(self) -> List[SelfTest]:
        """
        Get all registered tests.

        Returns:
            List of registered SelfTest instances.
        """
        return list(self._tests.values())

    def run_all(self) -> List[SelfTestResult]:
        """
        Run all registered tests.

        Returns:
            List of SelfTestResult objects.
        """
        results = []
        for test in self._tests.values():
            try:
                result = test.run()
                results.append(result)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error running self-test %s: %s", test.name, e)
                results.append(
                    SelfTestResult(
                        name=test.name,
                        success=False,
                        message=f"Test failed with exception: {str(e)}",
                        details={"exception": str(e)},
                    )
                )
        return results


# Global registry instance
registry = SelfTestRegistry()
