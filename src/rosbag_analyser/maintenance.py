"""Root-owned deployment gate shared by the API and worker."""
from pathlib import Path


MAINTENANCE_FILE = Path("/run/rosbag-analyser-maintenance")


def deployment_in_progress() -> bool:
    return MAINTENANCE_FILE.exists()
