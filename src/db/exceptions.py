"""
Domain exceptions for the db module.

Isolates the aiomysql driver from the public surface — no layer above
repository needs to import aiomysql to handle errors.
"""


class DatabaseError(RuntimeError):
    """Database access error (replaces aiomysql.Error at the public surface)."""


class QueryTimeoutError(TimeoutError):
    """Query exceeded the configured timeout — allows specific retry handling."""
