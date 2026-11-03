"""ABOUTME: A stdlib HTTP server that answers every request with a geo payload after a fixed delay.
ABOUTME: The starter serves it on 127.0.0.1 for one run, standing in for a provider that has slowed down.

The healthy fleet talks to the real geo providers, which answer in milliseconds, so the bug in
get_location stays hidden. The bad run points get_location at this server instead. It answers
every GET with a valid location payload, but only after ``delay_seconds``.
"""

from __future__ import annotations

import contextlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

LOCATION_PAYLOAD: dict[str, str] = {"city": "Austin", "region": "Texas", "country_name": "United States"}
"""Body returned for every request, in the shape of the ipapi.co provider."""


class SlowUpstream(ThreadingHTTPServer):
    """A threaded HTTP server whose handler waits delay_seconds before it answers."""

    def __init__(self, delay_seconds: float) -> None:
        """Bind to a free port on 127.0.0.1.

        Args:
            delay_seconds: Seconds each request waits before the response is sent.
        """
        super().__init__(("127.0.0.1", 0), _SlowHandler)
        self.delay_seconds = delay_seconds
        self.stopping = threading.Event()


class _SlowHandler(BaseHTTPRequestHandler):
    """Waits for the server's delay, then answers with LOCATION_PAYLOAD."""

    def do_GET(self) -> None:
        """Answer a GET after the configured delay, or at once if the server is stopping."""
        if not isinstance(self.server, SlowUpstream):
            raise TypeError(f"expected SlowUpstream, got {type(self.server).__name__}")
        self.server.stopping.wait(self.server.delay_seconds)
        body = json.dumps(LOCATION_PAYLOAD).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Stay quiet; the starter's output is the reader's view of the run."""


@contextlib.contextmanager
def serve_slow_upstream(delay_seconds: float) -> Iterator[str]:
    """Serve the slow endpoint on 127.0.0.1 for the duration of the with block.

    Args:
        delay_seconds: Seconds each request waits before it is answered.

    Yields:
        The base URL of the running server, for example ``http://127.0.0.1:41823``.
    """
    server = SlowUpstream(delay_seconds)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.stopping.set()
        server.shutdown()
        server.server_close()
        thread.join()
