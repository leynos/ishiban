"""Reap asyncio tasks owned by a response stream or metadata service."""

import asyncio
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc


async def cancel_and_reap[Result](tasks: cabc.Iterable[asyncio.Task[Result]]) -> None:
    """Cancel pending owned tasks and await their teardown.

    For example, closing a batch stream reaps its request waiters while a
    shared subprocess remains owned by the observer service.
    """
    owned = tuple(tasks)
    for task in owned:
        if not task.done():
            task.cancel()
    if owned:
        await asyncio.gather(*owned, return_exceptions=True)


def singleflight_task[Key, Result](
    inflight: dict[Key, asyncio.Task[Result]],
    key: Key,
    *,
    capacity: int,
    load: cabc.Callable[[Key], cabc.Coroutine[object, object, Result]],
) -> asyncio.Task[Result] | None:
    """Reuse or start one keyed task within the caller's pending-work bound.

    For example, the same session and execution watermark share one task,
    while a new key is unavailable when all permitted slots are occupied.

    Returns
    -------
    asyncio.Task[Result] or None
        The shared task, or no slot for a new key.
    """
    task = inflight.get(key)
    if task is not None:
        return task
    if len(inflight) >= capacity:
        return None
    task = asyncio.create_task(load(key))
    inflight[key] = task

    def forget(done: asyncio.Task[Result]) -> None:
        """Remove only the task still owning this key."""
        if inflight.get(key) is done:
            del inflight[key]

    task.add_done_callback(forget)
    return task
