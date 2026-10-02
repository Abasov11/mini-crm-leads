"""Простейшая шина событий внутри процесса: веб-страницы подписываются через SSE."""
import asyncio

_subs: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subs.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subs.discard(q)


def publish(kind: str, lead_id: int) -> None:
    for q in list(_subs):
        try:
            q.put_nowait({"kind": kind, "lead_id": lead_id})
        except asyncio.QueueFull:
            pass
