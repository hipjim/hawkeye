"""Docker container log source."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime

from .base import LogLine, LogSource


class DockerSource(LogSource):
    """Watch logs from a Docker container."""

    def __init__(self, container: str, tail: int = 0):
        """
        Initialize Docker log source.

        Args:
            container: Container name or ID
            tail: Number of existing lines to show (0 = none, -1 = all)
        """
        self.container_name = container
        self.tail = tail
        self._stop = False
        self._container = None
        super().__init__(name=f"docker:{container}")

    async def stream(self) -> AsyncIterator[LogLine]:
        """Stream logs from the Docker container."""
        try:
            import docker
        except ImportError:
            raise ImportError("docker package required: pip install docker")

        loop = asyncio.get_event_loop()

        # Connect to Docker in a thread pool
        client = await loop.run_in_executor(None, docker.from_env)

        try:
            self._container = await loop.run_in_executor(
                None, client.containers.get, self.container_name
            )
        except docker.errors.NotFound:
            raise ValueError(f"Container not found: {self.container_name}")

        # Get log stream
        tail_arg = "all" if self.tail == -1 else self.tail
        log_stream = self._container.logs(
            stream=True,
            follow=True,
            tail=tail_arg,
            timestamps=True,
        )

        # Process logs in executor to avoid blocking
        def get_next_line():
            try:
                return next(log_stream)
            except StopIteration:
                return None

        while not self._stop:
            line = await loop.run_in_executor(None, get_next_line)
            if line is None:
                break

            decoded = line.decode("utf-8", errors="replace").rstrip("\n")
            # Docker timestamps are at the start of the line
            # Format: 2024-01-05T10:30:00.123456789Z message
            if " " in decoded and decoded[0].isdigit():
                ts_str, content = decoded.split(" ", 1)
                try:
                    # Parse Docker timestamp
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except ValueError:
                    ts = datetime.now()
                    content = decoded
            else:
                ts = datetime.now()
                content = decoded

            yield LogLine(
                content=content,
                timestamp=ts,
                source=self.name,
            )

    async def close(self) -> None:
        """Stop watching container logs."""
        self._stop = True
