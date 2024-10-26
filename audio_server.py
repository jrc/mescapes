import http.server
import logging
import os
import socket
import socketserver
import threading
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)


def get_host_ip_address() -> str:
    """Return the local IP address by creating a temporary connection to a public DNS"""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


class AudioServer:
    """HTTP server for streaming audio files to Sonos speakers"""

    class _RequestHandler(http.server.BaseHTTPRequestHandler):
        def _handle_request(self):
            logger.debug(f"{self.command} {self.path}")

            file_path = os.path.join("assets", urllib.parse.unquote(self.path)[1:])

            if not os.path.isfile(file_path):
                return self.send_error(404, "File Not Found")

            # Send headers
            self.send_response(200)
            self.send_header("Content-type", "audio/mpeg")
            if self.command == "HEAD":
                self.send_header("Content-Length", str(os.path.getsize(file_path)))
            self.end_headers()

            # Send body
            if self.command == "GET":
                try:
                    with open(file_path, "rb") as f:
                        self.wfile.write(f.read())
                except (BrokenPipeError, ConnectionResetError):
                    logger.debug("Client closed connection")

        def do_HEAD(self):
            self._handle_request()

        def do_GET(self):
            self._handle_request()

    def __init__(self):
        self.host_ip = get_host_ip_address()
        self._server: Optional[socketserver.TCPServer] = None
        self._port: Optional[int] = None

    def start(self, port: int = 8000) -> None:
        self._port = port
        self._server = type(
            "TCPServerReuse", (socketserver.TCPServer,), {"allow_reuse_address": True}
        )(("", port), self._RequestHandler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        logger.info(f"Audio server started on port {port}")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            logger.info("Audio server stopped")

    def get_url(self, file_path: str) -> str:
        if not self._port:
            raise RuntimeError("Server not started")
        if file_path.startswith("./assets/"):
            file_path = file_path[len("./assets/") :]
        return f"http://{self.host_ip}:{self._port}/{urllib.parse.quote(file_path)}"
