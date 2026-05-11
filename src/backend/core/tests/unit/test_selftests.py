"""Tests for the selftest system."""

from core.selftests import SelfTest, SelfTestRegistry, SelfTestResult


class DummySuccessTest(SelfTest):
    """A test that always succeeds."""

    name = "Dummy Success Test"
    description = "A test that always passes"

    def run(self) -> SelfTestResult:
        return SelfTestResult(
            name=self.name,
            success=True,
            message="Test passed successfully",
            duration_ms=10.0,
        )


class DummyFailureTest(SelfTest):
    """A test that always fails."""

    name = "Dummy Failure Test"
    description = "A test that always fails"

    def run(self) -> SelfTestResult:
        return SelfTestResult(
            name=self.name,
            success=False,
            message="Test failed as expected",
            duration_ms=5.0,
        )


class DummyExceptionTest(SelfTest):
    """A test that raises an exception."""

    name = "Dummy Exception Test"
    description = "A test that throws an exception"

    def run(self) -> SelfTestResult:
        raise RuntimeError("This test is designed to fail")


def test_register_test():
    """Test that a test can be registered."""
    registry = SelfTestRegistry()
    registry.register(DummySuccessTest)

    tests = registry.get_all_tests()

    assert len(tests) == 1
    assert isinstance(tests[0], DummySuccessTest)


def test_register_multiple_tests():
    """Test that multiple tests can be registered."""
    registry = SelfTestRegistry()
    registry.register(DummySuccessTest)
    registry.register(DummyFailureTest)

    tests = registry.get_all_tests()

    assert len(tests) == 2


def test_unregister_test():
    """Test that a test can be unregistered."""
    registry = SelfTestRegistry()
    registry.register(DummySuccessTest)
    registry.unregister(DummySuccessTest)

    tests = registry.get_all_tests()

    assert len(tests) == 0


def test_run_all_success():
    """Test running all tests when all pass."""
    registry = SelfTestRegistry()
    registry.register(DummySuccessTest)

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].success is True


def test_run_all_mixed():
    """Test running all tests with mixed results."""
    registry = SelfTestRegistry()
    registry.register(DummySuccessTest)
    registry.register(DummyFailureTest)

    results = registry.run_all()

    assert len(results) == 2
    assert results[0].success is True
    assert results[1].success is False


def test_run_all_with_exception():
    """Test that exceptions are caught and converted to failures."""
    registry = SelfTestRegistry()
    registry.register(DummyExceptionTest)

    results = registry.run_all()

    assert len(results) == 1
    assert results[0].success is False
    assert "exception" in results[0].message.lower()


def test_result_to_dict():
    """Test converting a result to a dictionary."""
    result = SelfTestResult(
        name="Test Name",
        success=True,
        message="Test message",
        details={"key": "value"},
        duration_ms=100.5,
    )

    result_dict = result.to_dict()

    assert result_dict["name"] == "Test Name"
    assert result_dict["success"] is True
    assert result_dict["message"] == "Test message"
    assert result_dict["details"]["key"] == "value"
    assert result_dict["duration_ms"] == 100.5


def test_result_without_optional_fields():
    """Test creating a result without optional fields."""
    result = SelfTestResult(
        name="Test Name",
        success=False,
        message="Test failed",
    )

    result_dict = result.to_dict()

    assert result_dict["details"] == {}
    assert result_dict["duration_ms"] is None
