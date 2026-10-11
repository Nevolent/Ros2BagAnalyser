"""Contracts at the pinned llama.cpp chat-completion boundary."""
import json

import pytest

from rosbag_analyser.ai_description import validated_result
from rosbag_analyser.model_runtime import FRAME_COUNT
from rosbag_analyser.processors.qwen_inference import completion_request, CUES


def test_completion_supplies_the_schema_at_the_llama_cpp_json_schema_path():
    request = completion_request([b"png"] * FRAME_COUNT, list(range(FRAME_COUNT)))
    # The pinned server reads response_format.json_schema.schema. A sibling
    # response_format.schema silently becomes unconstrained JSON instead.
    schema = request["response_format"]["json_schema"]["schema"]
    assert request["response_format"]["type"] == "json_schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["objects"]["maxItems"] == 2
    assert set(schema["required"]) == {"environment", "objects", *CUES}
    assert all(schema["properties"][cue]["type"] == "boolean" for cue in CUES)


def test_overlong_object_list_from_unconstrained_generation_is_still_rejected():
    evidence = {"environment": "office with shelves and a desk",
                "objects": ["checkerboard", "chair", "door", "bookshelf",
                            "box", "table", "monitor"],
                **{cue: False for cue in CUES}}
    with pytest.raises(ValueError, match="Objects must be short noun phrases"):
        validated_result(json.dumps(evidence))
