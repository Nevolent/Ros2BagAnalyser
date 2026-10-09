"""Use the production sampler while retaining the standalone experiment entrypoint."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from rosbag_analyser.processors.video_frames import sample_video_frames
