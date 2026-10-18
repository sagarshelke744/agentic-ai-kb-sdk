"""Context-local event sink used to surface pipeline progress (steps, LLM retries) to streams."""

from contextvars import ContextVar
from typing import Any, Callable, Optional

EventSink = Callable[[str, dict], None]

_sink: ContextVar[Optional[EventSink]] = ContextVar("agentic_kb_event_sink", default=None)


def set_event_sink(sink: Optional[EventSink]) -> Any:
    """Install a sink for the current context. Returns a token for reset_event_sink."""
    return _sink.set(sink)


def reset_event_sink(token: Any) -> None:
    _sink.reset(token)


def emit(event: str, **data: Any) -> None:
    """Emit an event to the active sink, if any. Never raises."""
    sink = _sink.get()
    if sink is None:
        return
    try:
        sink(event, data)
    except Exception:
        pass
