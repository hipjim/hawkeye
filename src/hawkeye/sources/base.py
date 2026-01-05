"""Base class for log sources."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime


@dataclass
class LogLine:
    """Represents a single log line."""

    content: str
    timestamp: datetime
    source: str

    def __str__(self) -> str:
        return self.content


class LogSource(ABC):
    """Abstract base class for log sources."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def stream(self) -> AsyncIterator[LogLine]:
        """Stream log lines from the source."""
        yield  # type: ignore

    async def close(self) -> None:
        """Clean up resources."""
        pass
