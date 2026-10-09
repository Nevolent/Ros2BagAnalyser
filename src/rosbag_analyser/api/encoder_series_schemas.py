from rosbag_analyser.encoder_series import (
    ENCODER_SERIES_DEFINITIONS, ENCODER_COMPONENT, EncoderSeriesDisplay,
)
from .imu_series_schemas import (
    ImuSeriesResponse as EncoderSeriesResponse, imu_series_response,
)


def encoder_series_response(
    recording_id: int, display: EncoderSeriesDisplay,
) -> EncoderSeriesResponse:
    return imu_series_response(
        recording_id, display,
        definitions=ENCODER_SERIES_DEFINITIONS,
        default_component=ENCODER_COMPONENT,
        route="encoder-series",
        label="Encoder",
    )
