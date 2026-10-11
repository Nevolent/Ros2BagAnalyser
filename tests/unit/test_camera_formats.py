from array import array
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.processors.front_preview import (
    DecodedImage, FrontPreviewProcessingError, _bgr_pixels,
    eligible_camera_image, uint16_camera_image,
)
from rosbag_analyser.topic_selection import usable_topics, is_uint16_camera_topic


def raw_message(*, width=3, height=2, offset=0):
    return SimpleNamespace(
        layout=SimpleNamespace(dim=[
            SimpleNamespace(label="height", size=height, stride=height * width),
            SimpleNamespace(label="width", size=width, stride=width),
        ], data_offset=offset),
        data=array("H", [99] * offset + [0, 256, 32768, 65535, 256, 0]),
    )


def test_uint16_camera_layout_produces_fixed_range_gray_and_has_no_capture_header():
    image = uint16_camera_image(raw_message(offset=1))
    assert (image.width, image.height, image.encoding, image.step) == (3, 2, "mono16", 6)
    assert image.record_timestamp_only and not image.header_stamp_available
    assert image.header_timestamp_ns is None
    pixels = _bgr_pixels(image)
    np.testing.assert_array_equal(pixels[:, :, 0], [[0, 1, 128], [255, 1, 0]])
    np.testing.assert_array_equal(pixels[:, :, 0], pixels[:, :, 1])
    np.testing.assert_array_equal(pixels[:, :, 1], pixels[:, :, 2])


@pytest.mark.parametrize("mutation", [
    lambda m: setattr(m.layout.dim[0], "label", "width"),
    lambda m: setattr(m.layout.dim[1], "stride", 0),
    lambda m: setattr(m.layout.dim[0], "size", 4097),
    lambda m: setattr(m.layout, "data_offset", -1),
    lambda m: setattr(m, "data", array("H", [1, 2])),
])
def test_ambiguous_or_malformed_uint16_camera_layout_is_rejected(mutation):
    message = raw_message()
    mutation(message)
    with pytest.raises(FrontPreviewProcessingError) as captured:
        uint16_camera_image(message)
    assert captured.value.code == "front_array_layout_invalid"


@pytest.mark.parametrize("endian", ["little", "big"])
def test_mono16_preserves_endianness_and_ignores_row_padding(endian):
    row = b"".join(v.to_bytes(2, endian) for v in [0, 32768, 65535]) + b"padding"
    image = DecodedImage(3, 2, "mono16", len(row), row * 2,
                         is_bigendian=endian == "big")
    pixels = _bgr_pixels(image)
    assert pixels[:, :, 0].tolist() == [[0, 128, 255], [0, 128, 255]]


def test_mono8_is_a_camera_input_but_ouster_measurements_remain_excluded():
    image = DecodedImage(2, 1, "mono8", 3, b"\x00\xff\x77")
    camera = TopicFact("/front_camera/image_raw", "sensor_msgs/msg/Image", "cdr", 2)
    measurement = replace(camera, name="/ouster/range_image")
    assert eligible_camera_image(image, camera)
    assert not eligible_camera_image(image, measurement)
    assert _bgr_pixels(image).tolist() == [[[0, 0, 0], [255, 255, 255]]]


def test_only_the_recorded_camera_array_topic_can_be_an_image_candidate():
    raw = TopicFact("/robot/front_camera/actually_raw_image", "std_msgs/msg/UInt16MultiArray", "cdr", 172)
    empty = replace(raw, name="/robot/front_camera/image_raw", message_type="sensor_msgs/msg/Image", message_count=0)
    arbitrary = replace(raw, name="/robot/sensors/values")
    assert is_uint16_camera_topic(raw)
    assert usable_topics((empty, arbitrary, raw), "sensor_msgs/msg/Image") == (raw,)


def test_lidar_measurement_images_do_not_create_a_front_camera_target():
    topics = tuple(TopicFact("/robot/ouster/" + name, "sensor_msgs/msg/Image", "cdr", 20)
                   for name in ("range_image", "signal_image", "reflec_image", "nearir_image"))
    assert usable_topics(topics, "sensor_msgs/msg/Image") == ()
