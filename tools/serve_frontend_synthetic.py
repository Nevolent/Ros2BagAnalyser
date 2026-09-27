#!/usr/bin/env python3
"""Serve the packaged React app in synthetic mode without backend infrastructure."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse


WEB_ROOT = Path(__file__).resolve().parents[1] / "src/rosbag_analyser/web/react"


class SyntheticFrontendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if not self._serve_special(include_body=True):
            super().do_GET()

    def do_HEAD(self) -> None:
        if not self._serve_special(include_body=False):
            super().do_HEAD()

    def _serve_special(self, *, include_body: bool) -> bool:
        url = urlparse(self.path)
        path = url.path
        if path == "/api" or path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND, "Synthetic mode has no backend API")
            return True
        if path == "/__synthetic_preview__":
            body = b"rosbag-analyser-synthetic\n"
            content_type = "text/plain; charset=utf-8"
        elif path in {"/", "/processing", "/processing/"} or path.startswith("/recordings/"):
            params = parse_qs(url.query)
            if params.get("synthetic") != ["1"]:
                params["synthetic"] = ["1"]
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", f"{path}?{urlencode(params, doseq=True)}")
                self.end_headers()
                return True
            body = (WEB_ROOT / "index.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        else:
            return False
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)
        return True

    def list_directory(self, path: str):
        self.send_error(HTTPStatus.NOT_FOUND)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=4173, type=int)
    arguments = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), SyntheticFrontendHandler)
    print(f"Synthetic workspace: http://127.0.0.1:{arguments.port}/?synthetic=1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
