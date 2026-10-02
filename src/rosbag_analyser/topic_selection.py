"""Shared scan/worker sensor discovery by ROS type."""
from .catalog.metadata import TopicFact
TOPIC_SELECTION_POLICY = "typed-streams-v1"

def usable_topics(topics, message_type: str) -> tuple[TopicFact, ...]:
    return tuple(sorted(
        (t for t in topics if t.message_type == message_type
         and t.serialization_format == "cdr" and t.message_count > 0),
        key=lambda t: (-t.message_count, t.name)))

def select_topic(topics, preferred: str, message_type: str) -> TopicFact | None:
    candidates = usable_topics(topics, message_type)
    if message_type == "sensor_msgs/msg/Image" and candidates:
        return candidates[0]
    matching = [t for t in candidates if t.name == preferred]
    if len(matching) == 1:
        return matching[0]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        return None  # Multiple IMUs may have different frames/calibration.
    matching = [t for t in topics if t.name == preferred]
    return matching[0] if len(matching) == 1 else None
