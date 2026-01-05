"""File-based log source with tail-like functionality."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import aiofiles

from .base import LogLine, LogSource


class FileSource(LogSource):
    """Watch a log file for new lines (like tail -f)."""

    def __init__(self, path: str | Path, follow: bool = True):
        self.path = Path(path)
        self.follow = follow
        self._stop = False
        super().__init__(name=str(self.path))

    async def stream(self) -> AsyncIterator[LogLine]:
        """Stream lines from the file, optionally following new additions."""
        if not self.path.exists():
            raise FileNotFoundError(f"Log file not found: {self.path}")

        async with aiofiles.open(self.path, mode="r") as f:
            # Go to end of file if following
            if self.follow:
                await f.seek(0, 2)  # Seek to end

            while not self._stop:
                line = await f.readline()
                if line:
                    yield LogLine(
                        content=line.rstrip("\n"),
                        timestamp=datetime.now(),
                        source=self.name,
                    )
                elif self.follow:
                    # No new line, wait a bit before checking again
                    await asyncio.sleep(0.1)
                else:
                    # Not following, we're done
                    break

    async def close(self) -> None:
        """Stop the file watcher."""
        self._stop = True
