"""Standalone, offline image or video descriptions; no dashboard integration."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from video_frames import sample_video_frames

ROOT = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(ROOT / ".cache/huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

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


def save_result(result: dict[str, str | bool], stem: str) -> Path:
    """Write the validated result only in the experiment's derived output folder."""
    output_dir = ROOT / "outputs"
    if output_dir.is_symlink():
        raise ValueError("Output folder must not be a symlink")
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f"{stem}-description.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_dir,
                                         prefix=".description-", suffix=".json",
                                         delete=False) as file:
            temporary = Path(file.name)
            json.dump(result, file, indent=2, ensure_ascii=False)
            file.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path,
                        help="One local video, or local image files in order")
    parser.add_argument("--prompt", help="Additional visual focus for the description")
    parser.add_argument("--max-new-tokens", type=int,
                        help="Output limit (default: 160 for video, 128 for images)")
    parser.add_argument("--frame-count", type=int, default=12,
                        help="Evenly spaced video frames (default: 12)")
    parser.add_argument("--max-side", type=int, default=640,
                        help="Longest sampled frame side in pixels (default: 640)")
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument("--seed", type=int, help="Optional sampling seed")
    args = parser.parse_args()
    if args.frame_count < 2 or args.frame_count > 24:
        parser.error("--frame-count must be between 2 and 24")
    if args.max_side < 64 or args.max_side > 1920:
        parser.error("--max-side must be between 64 and 1920")
    video_extensions = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
    is_video = len(args.inputs) == 1 and args.inputs[0].suffix.lower() in video_extensions
    if any(path.suffix.lower() in video_extensions for path in args.inputs) and not is_video:
        parser.error("Pass exactly one video, or only still images")
    max_new_tokens = (args.max_new_tokens if args.max_new_tokens is not None
                      else 160 if is_video else 128)
    if max_new_tokens < 1:
        parser.error("--max-new-tokens must be positive")
    if not (ROOT / "model/model.safetensors").is_file():
        parser.error("Model not downloaded; run ./setup.sh first")

    from PIL import Image, ImageOps
    images = []
    if is_video:
        try:
            images, timestamps = sample_video_frames(
                args.inputs[0], count=args.frame_count, max_side=args.max_side
            )
        except (OSError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        print(f"Sampled {len(images)} ordered frames at "
              f"{', '.join(f'{t:.1f}s' for t in timestamps)} "
              f"(max side {args.max_side}px).", file=sys.stderr, flush=True)
    for path in ([] if is_video else args.inputs):
        path = path.expanduser().absolute()
        if any(part.is_symlink() for part in [path, *path.parents]):
            parser.error(f"Image paths must not follow symlinks: {path}")
        try:
            with Image.open(path) as image:
                images.append(ImageOps.exif_transpose(image).convert("RGB"))
        except (OSError, ValueError) as exc:
            parser.error(f"Cannot read image {path}: {exc}")

    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA is unavailable; try --device cpu")
    if args.seed is not None:
        torch.manual_seed(args.seed)
    started = time.monotonic()
    print("Loading local Qwen3-VL-2B-Instruct...", file=sys.stderr, flush=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        ROOT / "model", dtype="auto", device_map=args.device,
        local_files_only=True,
    ).eval()
    processor = AutoProcessor.from_pretrained(ROOT / "model", local_files_only=True)
    prompt = DESCRIPTION_PROMPT
    if args.prompt:
        prompt += f" Additional visual focus: {args.prompt}"
    if is_video:
        content = [
            {"type": "text", "text": (
                f"These {len(images)} frames are in chronological order and belong "
                "to one video."
            )},
            {"type": "video", "video": images},
            {"type": "text", "text": prompt},
        ]
    else:
        content = [*[{"type": "image", "image": image} for image in images],
                   {"type": "text", "text": prompt}]
    messages = [
        {"role": "system", "content": [{"type": "text", "text": (
            "Follow the requested JSON format exactly. Environment is one "
            "short setting/terrain/background/lighting phrase, without objects, "
            "activity, or camera motion. Objects are separate noun phrases. "
            "Use booleans for the six visual cues."
        )}]},
        {"role": "user", "content": content},
    ]
    processor_kwargs = {}
    if is_video:
        processor_kwargs = {
            "do_sample_frames": False,
            "video_metadata": [{
                "total_num_frames": len(images),
                "fps": 1.0,
                "frames_indices": timestamps,
                "height": images[0].height,
                "width": images[0].width,
            }],
        }
    inputs = processor.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True,
        return_dict=True, return_tensors="pt", **processor_kwargs,
    ).to(model.device)
    loaded = time.monotonic()
    print(f"Device: {model.device}; dtype: {model.dtype}; generating...",
          file=sys.stderr, flush=True)
    with torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=max_new_tokens,
                                   do_sample=False, temperature=None,
                                   top_p=None, top_k=None)
    text = processor.batch_decode(
        generated[:, inputs.input_ids.shape[1]:], skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]
    try:
        result = validated_result(text)
        output = save_result(result, args.inputs[0].stem)
    except (OSError, ValueError) as exc:
        parser.error(f"Invalid or unsaved model result: {exc}. Raw response: {text!r}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Saved {output}", file=sys.stderr)
    print(f"Load/preprocess: {loaded - started:.1f}s; generation: "
          f"{time.monotonic() - loaded:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
