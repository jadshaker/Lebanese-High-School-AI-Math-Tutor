import asyncio
from collections import defaultdict
from typing import Any

_subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)


async def subscribe(session_id: str) -> asyncio.Queue[dict[str, Any]]:
    """Subscribe to events for a session. Returns a queue that receives events."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _subscribers[session_id].append(queue)
    return queue


def unsubscribe(session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Remove a subscriber queue for a session."""
    if session_id in _subscribers:
        _subscribers[session_id] = [
            q for q in _subscribers[session_id] if q is not queue
        ]
        if not _subscribers[session_id]:
            del _subscribers[session_id]


async def publish(session_id: str, event: dict[str, Any]) -> None:
    """Publish an event to all subscribers of a session."""
    for queue in _subscribers.get(session_id, []):
        await queue.put(event)
