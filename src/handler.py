"""
Shared tool/resource error-handling helper.

run_tool centralises the try/except policy so every tool and resource
delegates to a single place instead of repeating the same 3-branch block.
"""
import inspect
import logging
from collections.abc import Awaitable
from typing import TypeVar

from src.db.exceptions import DatabaseError, QueryTimeoutError
from src.rate_limiter import RateLimiter

T = TypeVar("T")

_rate_limiter: RateLimiter | None = None


def configure_rate_limiter(limiter: RateLimiter | None) -> None:
    global _rate_limiter
    _rate_limiter = limiter


def reset_rate_limiter() -> None:
    global _rate_limiter
    _rate_limiter = None


async def run_tool(
    name: str,
    coro: Awaitable[T],
    logger: logging.Logger,
) -> T:
    """Executes a repository coroutine with standard error handling.

    - ValueError       → logged as warning, re-raised as-is (validation / not-found).
    - QueryTimeoutError → logged as warning, raised as RuntimeError (timeout).
    - DatabaseError    → logged as error, raised as RuntimeError (driver failure).
    """
    if _rate_limiter is not None:
        try:
            await _rate_limiter.check()
        except RuntimeError:
            if inspect.isawaitable(coro):
                try:
                    coro.close()  # type: ignore[attr-defined,union-attr]
                except AttributeError:
                    pass
            raise
    try:
        return await coro
    except ValueError as exc:
        logger.warning("%s blocked: %s", name, exc)
        raise
    except QueryTimeoutError as exc:
        logger.warning("%s timed out: %s", name, exc)
        raise RuntimeError(str(exc)) from exc
    except DatabaseError as exc:
        logger.error("%s failed (DB): %s", name, exc)
        raise RuntimeError("Error accessing the database. Please try again.") from exc
