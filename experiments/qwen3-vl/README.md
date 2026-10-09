# Standalone Qwen3-VL video experiment

Official model: [Qwen/Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct).
Code and setup are versioned; model weights, caches and generated output stay
local and ignored. The experiment has its own Python environment and CUDA PyTorch.
Its prompt, formatter and frame sampler are shared with dashboard processing;
see [Development](../../docs/DEVELOPMENT.md) for worker configuration.

## Run in WSL

```bash
cd /home/kardo/projects/rosbag-dashboard/experiments/qwen3-vl
./describe /absolute/path/to/preview.mp4
./describe /absolute/path/to/preview.mp4 --max-side 448
./describe /absolute/path/to/preview.mp4 --prompt "Focus on visible equipment and obstacles."
```

The runner uses FFprobe and FFmpeg to read one local video and sample 12 evenly
spaced frames. It resizes them to a maximum side of 640 pixels, passes them as
one ordered video with approximate timestamps to Qwen. It prints JSON with a
`description` of at most two short sentences and a `bunker` boolean, and saves
the same JSON to `outputs/<video-stem>-description.json` in this folder. The
description focuses on the visible environment, objects and whether other robots,
people or active movement appear. The bunker value is true only when the model
confirms all three visible cues: gravel-like terrain, dark curtains and artificial
lighting. An optional `--prompt` adds visual focus without changing the JSON format.
`--frame-count` (2–24) and `--max-side` (64–1920) override the defaults. If GPU
memory is tight, lower `--max-side`. `--max-new-tokens` defaults to 160 for video.
No frames are saved. Inputs are read only; nothing is written beside the video.
The runner does not open ROS bags or interact with the dashboard. Invalid model
JSON fails without replacing a prior output. Sparse frames cannot prove everything
that happened between them. Model wording and bunker cues still need human review.
`figure8-video-description.txt` and `figure8-video-run.log` record an earlier
prose-format CUDA run on the ready front preview for `2025_11_04_figure8`.

Still images remain available for smoke tests: `./describe sample.png` or pass
multiple image paths in chronological order. These produce the same JSON schema.
`sample.png` is a synthetic smoke-test image; `sample-description.txt` records
an actual model response to it, not a real-camera evaluation. Offline single-image
and two-image inference passed locally on the RTX 4060 Ti using bfloat16. The
two-image check used the synthetic image twice; its output and timing are in
`multi-image-description.txt` and `multi-image-run.log`.

The runner is offline after setup. It uses the model's shipped generation
configuration, `dtype="auto"`, and automatic device placement. Still images retain
Qwen's quickstart output limit of 128 new tokens. `--seed` optionally seeds
sampling. Each invocation reloads the model. `--device cpu` is available but
considerably slower.

## Recreate or resume setup

```bash
./setup.sh
```

Python 3.10+ with venv support is required. Setup downloads CUDA 12.6 PyTorch 2.7.1
with matching Torchvision 0.22.1 and pinned Transformers 4.57.6 dependencies, then the original unquantized model
at revision `89644892e4d85e24eaac8bacfd4f463576704203` (about 4.26 GB of weights).
The download script checks each file size against repository metadata; the smoke
test additionally loads the actual weights and generates a description. `model-download.json` records the revision and
sizes; `requirements.lock` records the installed environment. Downloads resume
from this folder's cache. Network access is needed only during setup.

