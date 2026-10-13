"""The fixed Qwen description contract and identity of its front-preview input."""
from __future__ import annotations

import hashlib
import json
import re

from rosbag_analyser.model_runtime import RUNTIME_ID, FRAME_COUNT, MAX_FRAME_SIDE, MAX_NEW_TOKENS
from rosbag_analyser.thumbnail import THUMBNAIL_POLICY, thumbnail_cache_identity

DESCRIPTION_POLICY = f"ai-description-v3:{RUNTIME_ID}:{THUMBNAIL_POLICY}:shared-images:tokens{MAX_NEW_TOKENS}:prompt-v1:formatter-v1"
DESCRIPTION_PLANNER_IDENTITY = hashlib.sha256(DESCRIPTION_POLICY.encode()).hexdigest()
MAX_DESCRIPTION_BYTES = 8192


def description_cache_identity(front_identity: str) -> str:
    return hashlib.sha256(f"{front_identity}:{DESCRIPTION_POLICY}".encode()).hexdigest()


def validate_description_result(value: object) -> dict[str, str | bool]:
    if (not isinstance(value, dict) or set(value) != {"description", "bunker"}
            or not isinstance(value["description"], str)
            or not value["description"].strip() or len(value["description"]) > 1000
            or any(ord(c) < 32 for c in value["description"])
            or type(value["bunker"]) is not bool):
        raise ValueError("Invalid AI description result")
    return value


def validate_description_manifest(manifest: dict) -> None:
    front = manifest.get("visual_source_identity")
    if (manifest.get("schema_version") != 2
            or manifest.get("artifact_kind") != "ai_description"
            or manifest.get("processor_version") != DESCRIPTION_POLICY
            or not isinstance(front, str) or len(front) != 64
            or any(c not in "0123456789abcdef" for c in front)
            or manifest.get("cache_identity") != description_cache_identity(front)
            or manifest.get("thumbnail_identity") != thumbnail_cache_identity(front)
            or not isinstance(manifest.get("output"), dict)
            or manifest["output"].get("file_name") != "description.json"):
        raise ValueError("Invalid AI description provenance")
    validate_description_result(manifest.get("result"))


DESCRIPTION_PROMPT = (
    "Return exactly one JSON object with these keys: environment (string), "
    "objects (array of strings), "
    "gravel_like_terrain (boolean), dark_curtains (boolean), "
    "artificial_lighting (boolean), other_robots_visible (boolean), "
    "people_visible (boolean), independent_movement_visible (boolean). "
    "No Markdown or other text. Environment is one short noun phrase of at most "
    "22 words describing only the setting, terrain, background, and lighting. "
    "Do not mention objects, people, robots, activity, or their absence there. "
    "Objects is an array of up to two short noun phrases naming distinct props "
    "or obstacles placed on the ground when visible; use an empty array if none. "
    "Do not list ground material, curtains, or "
    "lights as objects. The program "
    "builds the final description from these fields. "
    "Mention only visually supported details. Do not mention a location, "
    "purpose, bunker, robot inferred from the camera, camera movement, or "
    "events between sampled frames. Independent movement means a person, "
    "robot, or object visibly moving relative to the scene; apparent movement "
    "caused by the camera does not count. Mark each boolean true only when "
    "that feature is visibly supported; otherwise mark it false. "
    "Gravel-like terrain means a granular or regolith-like ground surface. "
    "Dark curtains means visible dark fabric curtains or drapes. "
    "Artificial lighting means the scene is visibly lit by artificial lights. "
    "Use JSON booleans true and false, not strings. Inspect the terrain for "
    "distinct stationary props or obstacles; include only what is clearly visible."
)


def _joined(items: list[str], conjunction: str = "and") -> str:
    if len(items) < 3:
        return f" {conjunction} ".join(items)
    return ", ".join(items[:-1]) + f", {conjunction} " + items[-1]


def validated_result(raw: str) -> dict[str, str | bool]:
    """Keep only the requested fields and require all three bunker cues."""
    try:
        evidence = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Model did not return a JSON object") from exc
    expected = {"environment", "objects", "gravel_like_terrain", "dark_curtains",
                "artificial_lighting", "other_robots_visible", "people_visible",
                "independent_movement_visible"}
    if not isinstance(evidence, dict) or set(evidence) != expected:
        raise ValueError("Model returned unexpected JSON fields")
    environment = evidence["environment"]
    if not isinstance(environment, str):
        raise ValueError("Environment must be a string")
    environment = environment.strip().rstrip(".!? ")
    if (not environment or "\n" in environment or len(environment.split()) > 22
            or re.search(r"[.!?]", environment)):
        raise ValueError("Environment must be one short phrase")
    objects = evidence["objects"]
    if (not isinstance(objects, list) or len(objects) > 4
            or any(not isinstance(item, str) or not item.strip()
                   or len(item.split()) > 6 or re.search(r"[.!?\n]", item)
                   for item in objects)):
        raise ValueError("Objects must be short noun phrases")
    features = expected - {"environment", "objects"}
    if any(type(evidence[feature]) is not bool for feature in features):
        raise ValueError("Visual evidence must use JSON booleans")
    activity = {
        "other robots": evidence["other_robots_visible"],
        "people": evidence["people_visible"],
        "active movement": evidence["independent_movement_visible"],
    }
    visible = [name for name, present in activity.items() if present]
    absent = [name for name, present in activity.items() if not present]
    if not visible:
        activity_sentence = "No other robots, people, or active movement are visible."
    elif not absent:
        activity_sentence = "Other robots, people, and active movement are visible."
    else:
        activity_sentence = (f"{_joined(visible).capitalize()} "
                             f"{'is' if visible == ['active movement'] else 'are'} "
                             f"visible; no {_joined(absent, 'or')} "
                             f"{'is' if absent == ['active movement'] else 'are'} visible.")
    bunker_features = ("gravel_like_terrain", "dark_curtains", "artificial_lighting")
    objects = [item.strip() for item in objects if not re.search(
        r"\b(?:lights?|curtains?|drapes?|gravel|terrain)\b", item, re.I
    )][:2]
    objects = [
        item if re.match(r"(?:a|an|the|one|several|some|multiple|two|three)\b", item, re.I)
        or item.split()[-1].endswith("s") else f"{'an' if item[0].lower() in 'aeiou' else 'a'} {item}"
        for item in objects
    ]
    scene = f"{environment}, featuring {_joined(objects)}" if objects else environment
    scene = scene[0].upper() + scene[1:]
    return {"description": f"{scene}. {activity_sentence}",
            "bunker": all(evidence[feature] for feature in bunker_features)}
