"""A source-free example: ./vm run tools/diagnostics/runtime_info.py."""
import importlib.metadata
import json
import os
import platform

print(json.dumps({
    "python": platform.python_version(),
    "ros_distro": os.environ.get("ROS_DISTRO"),
    "application_version": importlib.metadata.version("rosbag-analyser"),
}, indent=2))
