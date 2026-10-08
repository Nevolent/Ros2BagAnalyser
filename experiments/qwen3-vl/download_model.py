"""Download the official model at one fixed revision into this experiment."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(ROOT / ".cache/huggingface")
from huggingface_hub import HfApi, snapshot_download

MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"
REVISION = "89644892e4d85e24eaac8bacfd4f463576704203"

if __name__ == "__main__":
    info = HfApi().model_info(MODEL_ID, revision=REVISION, files_metadata=True)
    snapshot_download(repo_id=MODEL_ID, revision=REVISION,
                      local_dir=ROOT / "model", max_workers=2,
                      ignore_patterns=[".gitattributes"])
    sizes = {}
    for file in info.siblings:
        if file.rfilename == ".gitattributes":
            continue
        path = ROOT / "model" / file.rfilename
        if not path.is_file() or path.stat().st_size != file.size:
            raise RuntimeError(f"Incomplete download: {file.rfilename}")
        sizes[file.rfilename] = file.size
    metadata = {"model_id": MODEL_ID, "revision": info.sha, "files": sizes}
    (ROOT / "model-download.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Downloaded and size-checked {len(sizes)} files from {MODEL_ID}@{info.sha}")
