# backend_ml/agent/checkpointer.py
"""MongoDB-backed LangGraph checkpointer for durable, resumable runs.

Installed version: langgraph-checkpoint-mongodb 0.4.0.

This version ships only a synchronous ``MongoDBSaver`` (no async variant /
no ``aio`` submodule).  ``MongoDBSaver`` exposes async wrappers for all
checkpoint operations (``aget_tuple``, ``aput``, ``aput_writes``) via
``run_in_executor``, so it is fully compatible with async LangGraph graphs.

The class-level ``from_conn_string`` is a **synchronous** context manager
(``@contextmanager``), which means we enter it with a plain ``with`` block
inside an ``asynccontextmanager`` wrapper, then yield the saver to async
callers.

Usage:
    async with mongo_checkpointer() as cp:
        app = build_refresh_graph(..., checkpointer=cp)
        await app.ainvoke(state, {"configurable": {"thread_id": run_id}})
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.checkpoint.mongodb import MongoDBSaver


@asynccontextmanager
async def mongo_checkpointer(
    uri: str | None = None, db_name: str = "equitable"
) -> AsyncIterator[MongoDBSaver]:
    """Yield a MongoDBSaver bound to the given database.

    Args:
        uri:     MongoDB connection string.  Falls back to the ``MONGO_URI``
                 environment variable when not provided.
        db_name: Database to store checkpoint collections in.  Defaults to
                 ``"equitable"``; use ``"equitable_test"`` in tests so that
                 the ``test_db`` fixture drops them automatically.

    Yields:
        MongoDBSaver: A LangGraph checkpoint saver ready for use as
        ``checkpointer=cp`` in ``build_refresh_graph``.
    """
    from langgraph.checkpoint.mongodb import MongoDBSaver

    conn = uri or os.getenv("MONGO_URI")
    # from_conn_string is a *synchronous* context manager — enter it with
    # a plain ``with`` block; the saver is then safe to pass to async code.
    with MongoDBSaver.from_conn_string(conn, db_name=db_name) as saver:
        yield saver
