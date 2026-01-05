"""Docker container log source."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from queue import Queue, Empty
from threading import Thread

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
        self._line_queue: Queue[str | None] = Queue()
        self._reader_thread: Thread | None = None
        super().__init__(name=f"docker:{container}")

    def _read_logs(self, container, tail_arg) -> None:
        """Background thread to read Docker logs."""
        try:
            log_stream = container.logs(
                stream=True,
                follow=True,
                tail=tail_arg,
                timestamps=True,
            )

            buffer = ""
            for chunk in log_stream:
                if self._stop:
                    break

                # Decode chunk and add to buffer
                buffer += chunk.decode("utf-8", errors="replace")

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line:
                        self._line_queue.put(line)

            # Don't forget remaining buffer content
            if buffer and not self._stop:
                self._line_queue.put(buffer)

        except Exception as e:
            if not self._stop:
                self._line_queue.put(f"ERROR: {e}")
        finally:
            self._line_queue.put(None)  # Signal end of stream

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

        # Start background reader thread
        tail_arg = "all" if self.tail == -1 else self.tail
        self._reader_thread = Thread(
            target=self._read_logs,
            args=(self._container, tail_arg),
            daemon=True,
        )
        self._reader_thread.start()

        # Read from queue
        while not self._stop:
            try:
                # Non-blocking get with timeout
                line = await loop.run_in_executor(
                    None, lambda: self._line_queue.get(timeout=0.1)
                )

                if line is None:
                    break  # End of stream

                # Docker timestamps are at the start of the line
                # Format: 2024-01-05T10:30:00.123456789Z message
                if " " in line and len(line) > 0 and line[0].isdigit():
                    ts_str, content = line.split(" ", 1)
                    try:
                        # Parse Docker timestamp (handle nanoseconds)
                        # Truncate nanoseconds to microseconds for Python
                        if "." in ts_str:
                            base, frac = ts_str.rsplit(".", 1)
                            frac = frac.rstrip("Z")[:6]  # Keep only 6 digits
                            ts_str = f"{base}.{frac}+00:00"
                        else:
                            ts_str = ts_str.replace("Z", "+00:00")
                        ts = datetime.fromisoformat(ts_str)
                    except ValueError:
                        ts = datetime.now()
                        content = line
                else:
                    ts = datetime.now()
                    content = line

                yield LogLine(
                    content=content,
                    timestamp=ts,
                    source=self.name,
                )

            except Empty:
                continue
            except Exception:
                break

    async def close(self) -> None:
        """Stop watching container logs."""
        self._stop = True
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
