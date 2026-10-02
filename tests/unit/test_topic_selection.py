from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.topic_selection import select_topic, usable_topics

IMAGE = "sensor_msgs/msg/Image"
IMU = "sensor_msgs/msg/Imu"

def topic(name, count=100, kind=IMAGE, serialization="cdr"):
    return TopicFact(name, kind, serialization, count)

def test_camera_discovery_ignores_names_and_orders_all_nonempty_raw_streams():
    topics = (topic("/configured", 0), topic("/unusual/b", 800),
              topic("/unusual/a", 800), topic("/other", 30),
              topic("/compressed", 9000, "sensor_msgs/msg/CompressedImage"),
              topic("/unsupported", 9999, serialization="other"))
    assert [item.name for item in usable_topics(topics, IMAGE)] == [
        "/unusual/a", "/unusual/b", "/other"]
    assert select_topic(topics, "/configured", IMAGE).name == "/unusual/a"

def test_imu_fallback_requires_unique_type_or_valid_preference():
    first, second = topic("/sensor/a", kind=IMU), topic("/sensor/b", kind=IMU)
    assert select_topic((first,), "/missing", IMU) == first
    assert select_topic((first, second), "/missing", IMU) is None
    assert select_topic((first, second), second.name, IMU) == second
