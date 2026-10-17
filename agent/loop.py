import asyncio


def selector_loop_factory():
    """Event loop for uvicorn's `--loop` option.

    psycopg's async mode (used for the conversation store in Postgres) cannot run on the
    ProactorEventLoop that uvicorn picks by default on Windows.
    """
    return asyncio.SelectorEventLoop()
