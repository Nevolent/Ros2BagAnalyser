"""Standalone, offline image or video descriptions; no dashboard integration."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from video_frames import sample_video_frames

ROOT = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(ROOT / ".cache/huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

sys.path.insert(0, str(ROOT.parents[1] / "src"))
from rosbag_analyser.ai_description import DESCRIPTION_PROMPT, validated_result

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
