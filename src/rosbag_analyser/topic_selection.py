"""Shared scan/worker sensor discovery by ROS type."""
import re

from .catalog.metadata import TopicFact

TOPIC_SELECTION_POLICY = "typed-streams-v1"
UINT16_IMAGE_MESSAGE_TYPE = "std_msgs/msg/UInt16MultiArray"


def is_uint16_camera_topic(topic: TopicFact) -> bool:
    return (topic.message_type == UINT16_IMAGE_MESSAGE_TYPE
            and topic.name.endswith("/front_camera/actually_raw_image"))


def is_named_camera_topic(topic: TopicFact) -> bool:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", topic.name).lower()
    parts = re.split(r"[^a-z0-9]+", name)
    return "ouster" not in parts and any(part in parts for part in ("camera", "front"))


def is_ouster_measurement_topic(topic: TopicFact) -> bool:
    parts = topic.name.lower().split("/")
    return "ouster" in parts and parts[-1] in {
        "range_image", "signal_image", "reflec_image", "nearir_image"}


def _camera_order(topic: TopicFact) -> tuple[bool, bool, int, str]:
    # Match front as a name component, including camelCase camera names.
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", topic.name).lower()
    parts = re.split(r"[^a-z0-9]+", name)
    named_front = "front" in parts
    other_view = any(part in parts for part in ("ceiling", "top", "topdown", "rear", "back", "down"))
    return (other_view, not named_front, -topic.message_count, topic.name)


def usable_topics(topics, message_type: str) -> tuple[TopicFact, ...]:
    candidates = (
        topic for topic in topics
        if (topic.message_type == message_type
            or message_type == "sensor_msgs/msg/Image" and is_uint16_camera_topic(topic))
        and topic.serialization_format == "cdr" and topic.message_count > 0
    )
    if message_type == "sensor_msgs/msg/Image":
        return tuple(sorted((topic for topic in candidates
                             if not _camera_order(topic)[0] and not is_ouster_measurement_topic(topic)),
                            key=_camera_order))
    return tuple(sorted(candidates, key=lambda topic: (-topic.message_count, topic.name)))


def thumbnail_topics(topics) -> tuple[TopicFact, ...]:
    """Prefer front views, but allow other cameras for a fallback thumbnail."""
    return tuple(sorted((topic for topic in topics
                         if (topic.message_type == "sensor_msgs/msg/Image" or is_uint16_camera_topic(topic))
                         and topic.serialization_format == "cdr" and topic.message_count > 0
                         and not is_ouster_measurement_topic(topic)), key=_camera_order))


def select_topic(topics, preferred: str, message_type: str) -> TopicFact | None:
    candidates = usable_topics(topics, message_type)
    if message_type == "sensor_msgs/msg/Image":
        return candidates[0] if candidates else None
    matching = [t for t in candidates if t.name == preferred]
    if len(matching) == 1:
        return matching[0]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        return None  # Multiple IMUs may have different frames/calibration.
    matching = [t for t in topics if t.name == preferred]
    return matching[0] if len(matching) == 1 else None
