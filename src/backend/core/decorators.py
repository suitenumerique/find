"""Decorators for the core app."""

import logging
import time
from functools import wraps

from django.core.cache import cache

logger = logging.getLogger(__name__)


def throttle(max_calls, period):
    """
    Decorator to throttle function calls to a maximum rate.

    Uses a sliding window algorithm with Redis for distributed rate limiting.
    Works across multiple processes and servers.

    Args:
        max_calls: Maximum number of calls allowed in the time period (int)
        period: Time period in seconds (int)
    """

    def decorator(func):
        redis_key = f"throttle:{func.__module__}.{func.__name__}"

        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            window_timestamps = get_window_timestamps(redis_key, now - period)

            while len(window_timestamps) >= max_calls:
                wait_time = period - (now - min(window_timestamps))
                if wait_time > 0:
                    logger.info(
                        "Throttle limit reached for '%s' "
                        "(%d calls in %d seconds). Waiting %.2f seconds.",
                        redis_key,
                        max_calls,
                        period,
                        wait_time,
                    )
                    time.sleep(wait_time)

                    now = time.time()
                    # move the window after waiting
                    window_timestamps = get_window_timestamps(redis_key, now - period)

            window_timestamps.append(now)
            cache.set(redis_key, window_timestamps, timeout=period)

            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_window_timestamps(redis_key, window_start):
    """
    Get call timestamps within the time window.

    Args:
        redis_key: Redis cache key for the throttle
        window_start: Start timestamp of the sliding window

    Returns:
        List of timestamps for calls within the window
    """
    timestamps = cache.get(redis_key, [])
    return [ts for ts in timestamps if ts >= window_start]
