"""Synthetic coverage for short-video sampling in the shared production sampler."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from video_frames import sample_video_frames


class VideoFrameTests(unittest.TestCase):
    def test_more_samples_than_video_frames_keeps_the_final_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "synthetic.mp4"
            subprocess.run([
                "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                "testsrc2=size=320x240:rate=5:duration=2", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(video),
            ], check=True)
            before = video.stat()
            frames, timestamps = sample_video_frames(video, count=12, max_side=160)
            self.assertEqual(len(frames), 12)
            self.assertEqual(timestamps, sorted(timestamps))
            self.assertTrue(all(max(frame.size) <= 160 for frame in frames))
            self.assertAlmostEqual(timestamps[-1], 1.8, places=5)
            self.assertEqual(video.stat().st_mtime_ns, before.st_mtime_ns)
            self.assertEqual(list(Path(directory).iterdir()), [video])


if __name__ == "__main__":
    unittest.main()
