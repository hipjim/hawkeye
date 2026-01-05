"""Stdin log source for piped input."""

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import datetime

from .base import LogLine, LogSource


class StdinSource(LogSource):
    """Read log lines from stdin (for piped input)."""

    def __init__(self):
        super().__init__(name="stdin")
        self._stop = False

    async def stream(self) -> AsyncIterator[LogLine]:
        """Stream lines from stdin."""
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)

        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while not self._stop:
            try:
                line = await reader.readline()
                if not line:
                    break  # EOF
                yield LogLine(
                    content=line.decode().rstrip("\n"),
                    timestamp=datetime.now(),
                    source=self.name,
                )
            except Exception:
                break

    async def close(self) -> None:
        """Stop reading from stdin."""
        self._stop = True
