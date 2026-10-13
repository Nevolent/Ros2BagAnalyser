from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tarfile

import pytest

from rosbag_analyser import model_runtime as runtime, model_setup as setup
from rosbag_analyser.ai_description import validated_result
from rosbag_analyser.processors import qwen_inference as inference
from rosbag_analyser.processors.video_frames import sample_video_frames


@pytest.fixture
def installed(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    assets = {name: (len(name.encode()), hashlib.sha256(name.encode()).hexdigest())
              for name in runtime.MODEL_ASSETS}
    monkeypatch.setattr(runtime, "MODEL_ASSETS", assets)
    files = {}
    for relative, contents in [(f"model/{name}", name.encode()) for name in assets] + [
            ("bin/llama-server", b"#!/bin/sh\nexit 0\n")]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        path.chmod(0o555)
        files[relative] = {"size_bytes": path.stat().st_size,
                           "mtime_ns": path.stat().st_mtime_ns,
                           "sha256": runtime.file_sha256(path)}
    marker = root / "runtime.json"
    marker.write_text(json.dumps({"runtime_id": runtime.RUNTIME_ID,
                                 "model_revision": runtime.MODEL_REVISION,
                                 "llama_revision": runtime.LLAMA_REVISION, "files": files}))
    return root


def test_runtime_reuse_checks_bytes_without_downloading(installed, tmp_path, monkeypatch):
    runtime.validate_runtime(installed, verify_hashes=True)
    monkeypatch.setattr(setup, "download", lambda *a: pytest.fail("unexpected download"))
    setup.provision(installed, tmp_path / "cache")
    model = installed / "model" / runtime.MODEL_FILE
    original = model.stat()
    model.chmod(0o644)
    model.write_bytes(b"x" * original.st_size)
    os.utime(model, ns=(original.st_atime_ns, original.st_mtime_ns))
    with pytest.raises(ValueError, match="checksum"):
        setup.provision(installed, tmp_path / "cache")
    assert model.read_bytes() == b"x" * original.st_size


@pytest.mark.parametrize("change", ["identity", "missing", "escape", "symlink", "invalid"])
def test_untrusted_runtime_is_rejected(installed, change):
    marker = installed / "runtime.json"
    value = json.loads(marker.read_text())
    if change == "identity":
        value["llama_revision"] = "unknown"
    elif change == "missing":
        del value["files"]["bin/llama-server"]
    elif change == "escape":
        value["files"]["bin/../outside"] = {}
    elif change == "symlink":
        path = installed / "bin/llama-server"
        path.rename(installed / "outside")
        path.symlink_to(installed / "outside")
    else:
        value = []
    marker.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        runtime.validate_runtime(installed)


def test_bad_download_preserves_existing_cache_and_removes_partial(tmp_path, monkeypatch):
    cached = tmp_path / "weights"
    cached.write_bytes(b"previous")
    monkeypatch.setattr(setup.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"bad"))
    with pytest.raises(ValueError, match="checksum"):
        setup.download("https://example.invalid/model", cached, "0" * 64, 3)
    assert cached.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [cached]


def test_source_archive_cannot_escape_staging(tmp_path):
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w") as output:
        entry = tarfile.TarInfo("llama.cpp-" + runtime.LLAMA_REVISION + "/../../escape")
        entry.size = 1
        output.addfile(entry, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="unsafe"):
        setup.unpack_source(archive, tmp_path / "stage")
    assert not (tmp_path / "escape").exists()


def test_setup_rejects_source_storage_before_writing(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setenv("ROS_BAG_ANALYSER_ARCHIVE_ROOT", str(source))
    with pytest.raises(ValueError, match="separate from source"):
        setup.provision(source / "models", tmp_path / "cache")
    assert list(source.iterdir()) == [] and not (tmp_path / "cache").exists()


def evidence(**changes):
    value = {"environment": "an indoor area with gravel-like terrain, dark curtains and artificial lighting",
             "objects": ["a white sphere", "several rectangular blocks"],
             **{cue: cue in ("gravel_like_terrain", "dark_curtains", "artificial_lighting")
                for cue in inference.CUES}}
    return json.dumps(dict(value, **changes))


@pytest.mark.parametrize("cue", ["gravel_like_terrain", "dark_curtains", "artificial_lighting"])
def test_bunker_requires_every_cue(cue):
    assert validated_result(evidence())["bunker"] is True
    assert validated_result(evidence(**{cue: False}))["bunker"] is False


def test_formatter_retains_activity_and_filters_background_objects():
    result = validated_result(evidence(objects=["lights", "several rectangular blocks"], people_visible=True))
    assert "featuring several rectangular blocks." in result["description"]
    assert "People are visible; no other robots or active movement are visible." in result["description"]
    with pytest.raises(ValueError, match="booleans"):
        validated_result(evidence(dark_curtains="true"))


def test_completion_keeps_six_images_ordered_and_constrains_output():
    payload = inference.completion_request([bytes([i]) for i in range(6)], list(range(6)))
    content = payload["messages"][1]["content"]
    assert [part["text"] for part in content if part.get("text", "").startswith("Frame")] == [
        f"Frame {i + 1}, timestamp {i:.3f} seconds:" for i in range(6)]
    assert len([part for part in content if part["type"] == "image_url"]) == 6
    assert payload["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert payload["max_tokens"] == runtime.MAX_NEW_TOKENS
    partial = inference.completion_request([b"image"], [0])
    assert len([part for part in partial['messages'][1]['content'] if part['type'] == 'image_url']) == 1
    with pytest.raises(ValueError, match="frame policy"):
        inference.completion_request([], [])


@pytest.mark.parametrize("finish", ["stop", "length"])
def test_native_child_uses_private_socket_and_is_reaped(tmp_path, monkeypatch, finish):
    root = tmp_path / "runtime"
    (root / "bin").mkdir(parents=True)
    server = root / "bin/llama-server"
    # Exercise the real HTTP socket transport and real child lifecycle without weights.
    server.write_text('''#!/usr/bin/env python3
import json, socketserver, sys
from http.server import BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
    def do_GET(self): self.respond({"status": "ok"})
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert len([p for p in request['messages'][1]['content'] if p['type']=='image_url'])==6
        self.respond({"choices": [{"finish_reason": FINISH, "message": {"content": EVIDENCE}}]})
    def respond(self, data):
        body=json.dumps(data).encode(); self.send_response(200)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
class Server(socketserver.UnixStreamServer):
    def get_request(self):
        connection, address = super().get_request(); return connection, ('local', 0)
Server(sys.argv[sys.argv.index('--host')+1], Handler).serve_forever()
'''.replace("FINISH", repr(finish)).replace("EVIDENCE", repr(evidence())))
    server.chmod(0o755)
    monkeypatch.setattr(inference, "validate_runtime", lambda _: {})
    original = subprocess.Popen
    children = []
    def start(command, **kwargs):
        assert command[command.index("--device") + 1] == "none"
        assert "--no-mmproj-offload" in command
        assert "--port" not in command and command[command.index("--host") + 1].endswith(".sock")
        child = original(command, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(inference.subprocess, "Popen", start)
    before = set(Path("/tmp").glob("qwen-*"))
    if finish == "stop":
        assert inference.infer(root, [b"image"] * 6, list(range(6)), threads=4)["bunker"] is True
    else:
        with pytest.raises(ValueError, match="truncated"):
            inference.infer(root, [b"image"] * 6, list(range(6)), threads=4)
    assert children[0].poll() is not None
    assert set(Path("/tmp").glob("qwen-*")) == before


@pytest.mark.parametrize("count,side", [(6, 448), (12, 160)])
def test_sampling_is_bounded_read_only_and_keeps_sparse_final_frame(tmp_path, count, side):
    video = tmp_path / "synthetic.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=640x480:rate=5:duration=2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(video)], check=True)
    original = video.read_bytes(), video.stat().st_mtime_ns
    with video.open("rb") as stream:
        frames, times = sample_video_frames(video, count=count, max_side=side, video_fd=stream.fileno())
    assert len(frames) == count and times == sorted(times)
    assert all(max(struct.unpack(">II", frame[16:24])) <= side for frame in frames)
    assert times[-1] == pytest.approx(1.8, abs=0.1)
    assert (video.read_bytes(), video.stat().st_mtime_ns) == original
    assert list(tmp_path.iterdir()) == [video]
