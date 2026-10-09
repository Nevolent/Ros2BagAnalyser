from __future__ import annotations

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request


PROJECT_ROOT = Path(__file__).parents[2]


def test_api_shutdown_closes_stalled_media_without_waiting_for_browser(tmp_path):
    media = tmp_path / "synthetic.bin"
    with media.open("wb") as file:
        file.truncate(64 * 1024 * 1024)
    script = tmp_path / "serve.py"
    script.write_text(
        '''import os
import sys
from rosbag_analyser.api import app as api_module
from rosbag_analyser.api.range_file_response import RangeFileResponse

class Catalog:
    def list_recordings(self):
        raise AssertionError("Shutdown test must not read a catalog")

application = api_module.create_app(Catalog())

@application.get("/stalled")
async def stalled():
    descriptor = os.open(sys.argv[2], os.O_RDONLY)
    return RangeFileResponse(
        descriptor, media_type="application/octet-stream",
        stat_result=os.fstat(descriptor), executor=application.state.media_read_executor,
    )

run_uvicorn = api_module.uvicorn.run
def serve_fixture(app, **kwargs):
    kwargs["port"] = int(sys.argv[1])
    run_uvicorn(application, **kwargs)

api_module.uvicorn.run = serve_fixture
api_module.main()
'''
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(PROJECT_ROOT / "src"), env.get("PYTHONPATH")])
    )
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, str(script), str(port), str(media)],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health/live", timeout=0.2
                    ):
                        break
                except OSError:
                    assert process.poll() is None, "Synthetic API exited during startup"
                    time.sleep(0.05)
            else:
                raise AssertionError("Synthetic API did not listen")

            with socket.socket() as browser:
                browser.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
                browser.settimeout(2)
                browser.connect(("127.0.0.1", port))
                browser.sendall(b"GET /stalled HTTP/1.1\r\nHost: localhost\r\n\r\n")
                headers = b""
                while b"\r\n\r\n" not in headers:
                    chunk = browser.recv(1024)
                    assert chunk, "Media connection ended before headers"
                    headers += chunk
                assert b"200 OK" in headers
                # Leave the connection open without consuming its synthetic payload.
                time.sleep(0.2)
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=15)
                assert process.returncode in {0, -signal.SIGTERM}
                # The browser sees EOF before the promised payload completes.
                received = len(headers.split(b"\r\n\r\n", 1)[1])
                while chunk := browser.recv(65536):
                    received += len(chunk)
                assert received < media.stat().st_size
            log.seek(0)
            output = log.read()
            assert "timeout graceful shutdown exceeded" in output
            assert "Application shutdown complete" in output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
