"""Offline Qwen inference, executed only in the separately provisioned model environment."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

from rosbag_analyser.ai_description import DESCRIPTION_PROMPT, validated_result, validate_description_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-fd", type=int, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from rosbag_analyser.processors.video_frames import sample_video_frames
    images, timestamps = sample_video_frames(
        Path(f"/proc/self/fd/{args.video_fd}"), video_fd=args.video_fd,
        count=12, max_side=640, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe,
    )
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    print("Loading local Qwen3-VL-2B-Instruct...", file=sys.stderr, flush=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        args.model_root, dtype="auto", device_map="auto",
        local_files_only=True,
    ).eval()
    processor = AutoProcessor.from_pretrained(args.model_root, local_files_only=True)
    prompt = DESCRIPTION_PROMPT
    content = [
        {"type": "text", "text": f"These {len(images)} frames are in chronological order and belong to one video."},
        {"type": "video", "video": images},
        {"type": "text", "text": prompt},
    ]
    messages = [
        {"role": "system", "content": [{"type": "text", "text": (
            "Follow the requested JSON format exactly. Environment is one "
            "short setting/terrain/background/lighting phrase, without objects, "
            "activity, or camera motion. Objects are separate noun phrases. "
            "Use booleans for the six visual cues."
        )}]},
        {"role": "user", "content": content},
    ]
    processor_kwargs = {
        "do_sample_frames": False,
        "video_metadata": [{
            "total_num_frames": len(images), "fps": 1.0, "frames_indices": timestamps,
            "height": images[0].height, "width": images[0].width,
        }],
    }
    inputs = processor.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True,
        return_dict=True, return_tensors="pt", **processor_kwargs,
    ).to(model.device)
    print(f"Device: {model.device}; dtype: {model.dtype}; generating...",
          file=sys.stderr, flush=True)
    with torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=160,
                                   do_sample=False, temperature=None,
                                   top_p=None, top_k=None)
    text = processor.batch_decode(
        generated[:, inputs.input_ids.shape[1]:], skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]
    result = validate_description_result(validated_result(text))
    args.output.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
