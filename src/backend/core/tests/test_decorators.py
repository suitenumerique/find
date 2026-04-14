"""Test decorators"""

import time

from django.core.cache import cache

import pytest

from core.decorators import throttle

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def before_each():
    """Clear caches before each test"""
    cache.clear()
    yield
    cache.clear()


def test_throttle_basic():
    """Test basic throttling with fixed values"""

    max_calls = 3
    period = 1

    @throttle(max_calls=max_calls, period=period)
    def test_func():
        pass

    cache.delete("throttle:test_func")

    start = time.time()

    # First 3 calls should be fast
    for _ in range(max_calls):
        test_func()

    cached_timestamp = cache.get("throttle:core.tests.test_decorators.test_func")
    elapsed = time.time() - start

    assert elapsed < 0.01  # Should be very fast since we haven't hit the limit yet
    assert len(cached_timestamp) == max_calls  # the throttle has reached the max calls

    start = time.time()
    # 4th call should throttle
    test_func()

    cached_timestamp = cache.get("throttle:core.tests.test_decorators.test_func")
    total_elapsed = time.time() - start

    assert total_elapsed >= period  # Should have waited for the period to pass
    assert total_elapsed < period + 0.01
    assert len(cached_timestamp) <= max_calls


def test_throttle_window_sliding():
    """Test that old calls are removed from the window"""

    max_calls = 2
    period = 1

    @throttle(max_calls=max_calls, period=period)
    def test_func():
        pass

    for _ in range(max_calls):
        test_func()

    cached_timestamp = cache.get("throttle:core.tests.test_decorators.test_func")
    assert len(cached_timestamp) == max_calls

    # Wait for window to pass
    time.sleep(period)

    cached_timestamp = cache.get("throttle:core.tests.test_decorators.test_func")
    assert cached_timestamp is None

    start = time.time()

    for _ in range(max_calls):
        test_func()

    elapsed = time.time() - start
    cached_timestamp = cache.get("throttle:core.tests.test_decorators.test_func")

    assert len(cached_timestamp) == max_calls
    assert elapsed < 0.01


def test_throttle_no_interference():
    """Test that multiple throttled functions don't interfere"""

    max_calls = 2
    period = 1

    @throttle(max_calls=max_calls, period=period)
    def func1():
        pass

    @throttle(max_calls=max_calls, period=period)
    def func2():
        pass

    start = time.time()

    for _ in range(max_calls):
        func1()
        func2()

    elapsed = time.time() - start
    cached_timestamp_1 = cache.get("throttle:core.tests.test_decorators.func1")
    cached_timestamp_2 = cache.get("throttle:core.tests.test_decorators.func2")

    # Should be fast since they have separate keys
    assert elapsed < 0.01
    assert len(cached_timestamp_1) == max_calls
    assert len(cached_timestamp_2) == max_calls
