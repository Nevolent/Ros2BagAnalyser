from __future__ import annotations

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request

import pytest


NGINX_BINARY = os.environ.get("ROS_BAG_ANALYSER_TEST_NGINX")
pytestmark = pytest.mark.deployment


class ArtifactHandler(BaseHTTPRequestHandler):
    payload = b"identity-bound-content"

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _trusted_headers(self) -> bool:
        return (
            self.headers.get("Authorization") is None
            and self.headers.get("X-Forwarded-For") == "127.0.0.1"
            and self.headers.get("X-Forwarded-Proto") == "https"
        )

    def do_HEAD(self) -> None:
        if not self._trusted_headers():
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("ETag", '"current"')
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()

    def do_GET(self) -> None:
        if not self._trusted_headers():
            self.send_error(500)
            return
        if self.path == "/artifact/stale":
            self.send_response(409)
            self.end_headers()
            return
        range_header = self.headers.get("Range")
        if_range = self.headers.get("If-Range")
        if range_header == "bytes=0-0" and if_range == '"current"':
            self.send_response(206)
            self.send_header("Content-Range", f"bytes 0-0/{len(self.payload)}")
            body = self.payload[:1]
        else:
            self.send_response(200)
            body = self.payload
        self.send_header("ETag", '"current"')
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self._trusted_headers():
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def free_port() -> int:
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        return int(available.getsockname()[1])


def request(
    port: int,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> urllib.response.addinfourl:
    authorization = base64.b64encode(b"engineer:test-password").decode("ascii")
    request_headers = {
        "Host": "trial.lab.test",
        "Authorization": f"Basic {authorization}",
        **({} if headers is None else headers),
    }
    request_value = urllib.request.Request(
        f"https://127.0.0.1:{port}{path}",
        method=method,
        headers=request_headers,
        data=b"" if method == "POST" else None,
    )
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return urllib.request.urlopen(request_value, context=context, timeout=3)


@pytest.mark.skipif(not NGINX_BINARY, reason="disposable Nginx binary not configured")
def test_real_nginx_preserves_identity_delivery_and_access_boundary(
    tmp_path: Path,
) -> None:
    assert NGINX_BINARY is not None
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), ArtifactHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    proxy_port = free_port()
    certificate = tmp_path / "certificate.pem"
    private_key = tmp_path / "private.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=trial.lab.test",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
        ],
        check=True,
        capture_output=True,
    )
    password = subprocess.run(
        ["openssl", "passwd", "-6", "test-password"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    access = tmp_path / "access.htpasswd"
    access.write_text(f"engineer:{password}\n", encoding="ascii")

    repository = Path(__file__).parents[2]
    template = (
        repository / "deploy" / "nginx" / "rosbag-analyser.conf.template"
    ).read_text(encoding="utf-8")
    proxy_headers = (
        repository / "deploy" / "nginx" / "rosbag-analyser-proxy-headers.conf"
    )
    rendered = template.replace("trial.example.invalid", "trial.lab.test")
    rendered = re.sub(
        r"    listen 192\.0\.2\.10:443 ssl http2 default_server;\n"
        r"    listen \[2001:db8::10\]:443 ssl http2 default_server ipv6only=on;",
        f"    listen 127.0.0.1:{proxy_port} ssl default_server;",
        rendered,
    )
    rendered = rendered.replace(
        "server 127.0.0.1:8000;",
        f"server 127.0.0.1:{upstream.server_port};",
    )
    rendered = rendered.replace(
        "/etc/rosbag-analyser/tls/fullchain.pem", str(certificate)
    ).replace("/etc/rosbag-analyser/tls/private.key", str(private_key))
    rendered = rendered.replace(
        "/etc/rosbag-analyser/access/engineers.htpasswd", str(access)
    ).replace("/etc/rosbag-analyser/access/operators.htpasswd", str(access))
    rendered = rendered.replace(
        "/etc/nginx/rosbag-analyser-proxy-headers.conf", str(proxy_headers)
    )
    prefix = tmp_path / "nginx"
    prefix.mkdir()
    for child in ("body", "proxy", "fastcgi", "scgi", "uwsgi"):
        (prefix / child).mkdir()
    config = tmp_path / "nginx.conf"
    config.write_text(
        "worker_processes 1;\n"
        f"pid {prefix / 'nginx.pid'};\n"
        "error_log stderr notice;\n"
        "events { worker_connections 32; }\n"
        "http {\n"
        "  access_log off;\n"
        f"  client_body_temp_path {prefix / 'body'};\n"
        f"  proxy_temp_path {prefix / 'proxy'};\n"
        f"  fastcgi_temp_path {prefix / 'fastcgi'};\n"
        f"  scgi_temp_path {prefix / 'scgi'};\n"
        f"  uwsgi_temp_path {prefix / 'uwsgi'};\n"
        f"{rendered}\n"
        "}\n",
        encoding="utf-8",
    )
    syntax = subprocess.run(
        [NGINX_BINARY, "-p", str(prefix), "-c", str(config), "-t"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr
    process = subprocess.Popen(
        [NGINX_BINARY, "-p", str(prefix), "-c", str(config), "-g", "daemon off;"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(40):
            try:
                with request(proxy_port, "/artifact/current") as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("Nginx did not become ready")

        with request(proxy_port, "/artifact/current", method="HEAD") as response:
            assert response.status == 200
            assert response.headers["Accept-Ranges"] == "bytes"
            assert response.headers["ETag"] == '"current"'
        with request(
            proxy_port,
            "/artifact/current",
            headers={"Range": "bytes=0-0", "If-Range": '"current"'},
        ) as response:
            assert response.status == 206
            assert response.read() == b"i"
        with request(
            proxy_port,
            "/artifact/current",
            headers={"Range": "bytes=0-0", "If-Range": '"stale"'},
        ) as response:
            assert response.status == 200
            assert response.read() == ArtifactHandler.payload
        with pytest.raises(urllib.error.HTTPError) as stale:
            request(proxy_port, "/artifact/stale")
        assert stale.value.code == 409
        with pytest.raises(urllib.error.HTTPError) as cross_origin:
            request(
                proxy_port,
                "/api/v1/recordings/prepare",
                method="POST",
                headers={"Origin": "https://attacker.invalid"},
            )
        assert cross_origin.value.code == 403
        with request(
            proxy_port,
            "/api/v1/recordings/prepare",
            method="POST",
            headers={
                "Origin": "https://trial.lab.test",
                "X-Forwarded-For": "203.0.113.99",
            },
        ) as response:
            assert response.status == 200
        with pytest.raises(urllib.error.HTTPError) as docs:
            request(proxy_port, "/docs")
        assert docs.value.code == 404
    finally:
        process.terminate()
        process.wait(timeout=5)
        upstream.shutdown()
        upstream.server_close()
