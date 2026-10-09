"""Six wheel RPM channels from KuupKulgur EncodersStamped (RD01, pp. 6/8/15)."""
from pathlib import Path

from rosbag_analyser.imu_series import (
    ImuSeriesDefinition,
    ImuSourceResolver,
    ImuSeriesService,
    ImuSeriesDisplay,
    _cache_identity as telemetry_cache_identity,
)
from rosbag_analyser.persistence.processing_repository import (
    ENCODER_SERIES_KIND,
    ProcessingRepository,
)


PROCESSOR_VERSION = "encoder-series-v1"
ENCODER_MESSAGE_TYPE = "kuupkulgur_msgs/msg/EncodersStamped"
ENCODER_COMPONENT = "encoder.FL"
WHEEL_ORDER = ("FL", "FR", "ML", "MR", "RL", "RR")
WHEEL_LABELS = (
    "Front left", "Front right", "Middle left", "Middle right", "Rear left", "Rear right",
)
ENCODER_SERIES_DEFINITIONS = tuple(
    ImuSeriesDefinition(
        f"wheel_{wheel.lower()}", f"encoder.{wheel}",
        f"{label} ({wheel})", "RPM", index + 1,
    )
    for index, (wheel, label) in enumerate(zip(WHEEL_ORDER, WHEEL_LABELS))
)
ENCODER_SERIES_BY_COMPONENT = {
    definition.component: definition for definition in ENCODER_SERIES_DEFINITIONS
}


class EncoderSourceResolver(ImuSourceResolver):
    kind = ENCODER_SERIES_KIND
    message_type = ENCODER_MESSAGE_TYPE
    definitions = ENCODER_SERIES_DEFINITIONS
    series_by_component = ENCODER_SERIES_BY_COMPONENT
    processor_version = PROCESSOR_VERSION
    label = "encoder"
    prefix = "encoder"
    stream_description = "a KuupKulgur EncodersStamped stream"

    def __init__(
        self, archive_root: Path, repository: ProcessingRepository, topic_name: str = "",
    ) -> None:
        super().__init__(archive_root, repository, topic_name, ENCODER_COMPONENT)


class EncoderSeriesService(ImuSeriesService):
    """Use the shared telemetry lifecycle with an encoder resolver and store."""


EncoderSeriesDisplay = ImuSeriesDisplay


def encoder_cache_identity(record, metadata_identity, database_identity, topic, configured_topic):
    return telemetry_cache_identity(
        record, metadata_identity, database_identity, topic, configured_topic, ENCODER_COMPONENT,
        kind=ENCODER_SERIES_KIND,
        processor_version=PROCESSOR_VERSION,
        definitions=ENCODER_SERIES_DEFINITIONS,
    )
