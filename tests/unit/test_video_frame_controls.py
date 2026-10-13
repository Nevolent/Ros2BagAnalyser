import os
import sys
import time

import pytest

from rosbag_analyser.job_control import JobCanceled
from rosbag_analyser.processors.video_frames import _decode_command


def test_cancel_reaps_running_decoder(tmp_path):
    pid_path = tmp_path / "pid"
    class Control:
        calls = 0
        def checkpoint(self, phase):
            self.calls += 1
            if self.calls > 1:
                raise JobCanceled("Synthetic cancel")
    command = [sys.executable, "-c",
        "import os,time,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)", str(pid_path)]
    started = time.monotonic()
    with pytest.raises(JobCanceled):
        _decode_command(command, timeout=10, pass_fds=(), control=Control())
    assert time.monotonic() - started < 3
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_path.read_text()), 0)


def test_pause_stops_decoder_and_does_not_consume_active_timeout(tmp_path):
    marker = tmp_path / "completed"
    class Control:
        calls = 0
        def checkpoint(self, phase):
            self.calls += 1
            if self.calls == 2:
                time.sleep(0.6)
                assert not marker.exists(), "Decoder advanced while paused"
    command = [sys.executable, "-c",
        "import time,pathlib,sys; time.sleep(0.4); pathlib.Path(sys.argv[1]).write_text('done'); print('done')", str(marker)]
    result = _decode_command(command, timeout=0.7, pass_fds=(), control=Control())
    assert result.stdout == b"done\n" and marker.exists()
