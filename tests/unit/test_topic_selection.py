import pytest

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

@pytest.mark.parametrize("name", [
    "/front/image_raw", "/sensors/camera_front/color", "/FrontCamera/rgb",
    "/robot/front_left/image", "/camera/FRONT/image",
])
def test_named_front_camera_wins_over_busier_streams_without_configuration(name):
    front = topic(name, 20)
    topics = (topic("/waterfront/image", 5000), front, topic("/other/image", 800))
    assert usable_topics(topics, IMAGE)[0] == front
    assert select_topic(topics, "", IMAGE) == front


def test_camera_fallback_is_stable_when_metadata_order_changes():
    topics = (topic("/z/image", 800), topic("/a/image", 800), topic("/b/image", 50))
    assert usable_topics(topics, IMAGE) == usable_topics(reversed(topics), IMAGE)
    assert select_topic(topics, "", IMAGE).name == "/a/image"


def test_multiple_front_names_use_count_then_name_and_ignore_ineligible_types():
    topics = (topic("/front/compressed", 10000, "sensor_msgs/msg/CompressedImage"),
              topic("/front/empty", 0), topic("/front/z", 100),
              topic("/front/a", 100), topic("/front/slow", 30), topic("/rear", 5000))
    assert [item.name for item in usable_topics(topics, IMAGE)] == [
        "/front/a", "/front/z", "/front/slow"]


def test_ceiling_camera_is_not_a_front_input_even_with_front_prefix():
    main = topic('/camera/front/image_raw', 100)
    ceiling = topic('/front/ceiling_camera/image_raw', 5000)
    assert usable_topics((ceiling, main), IMAGE) == (main,)
    assert select_topic((ceiling,), '', IMAGE) is None


def test_configured_name_cannot_make_a_non_image_stream_eligible():
    configured = topic("/configured/front", kind=IMU)
    assert select_topic((configured,), configured.name, IMAGE) is None
