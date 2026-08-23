#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def request_json(base_url: str, path: str) -> dict[str, object]:
    with urllib.request.urlopen(base_url + path, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError("A smoke-check endpoint was not ready.")
        document = json.load(response)
    if not isinstance(document, dict):
        raise RuntimeError("A smoke-check endpoint returned an invalid document.")
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--recording-id", type=int)
    arguments = parser.parse_args()
    if arguments.base_url not in {
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://[::1]:8000",
    }:
        raise SystemExit("Local smoke checks require the approved loopback API.")
    before = request_json(arguments.base_url, "/api/v1/processing/overview")
    live = request_json(arguments.base_url, "/health/live")
    ready = request_json(arguments.base_url, "/health/ready")
    request_json(arguments.base_url, "/api/v1/catalog")
    if live.get("status") != "alive" or ready.get("status") != "ready":
        raise SystemExit("The local service is not ready.")
    if arguments.recording_id is not None:
        if arguments.recording_id <= 0:
            raise SystemExit("The optional recording ID must be positive.")
        detail = request_json(
            arguments.base_url,
            f"/api/v1/recordings/{arguments.recording_id}",
        )
        outputs = detail.get("outputs")
        if not isinstance(outputs, list):
            raise SystemExit("The recording detail is invalid.")
        for output in outputs:
            if not isinstance(output, dict) or output.get("state") != "ready":
                continue
            artifact = output.get("artifact")
            if not isinstance(artifact, dict) or not isinstance(artifact.get("url"), str):
                raise SystemExit("A ready output has no identity-bound URL.")
            url = arguments.base_url + artifact["url"]
            head = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(head, timeout=10) as response:
                if response.status != 200 or response.headers.get("Accept-Ranges") != "bytes":
                    raise SystemExit("Identity-bound HEAD delivery failed.")
            byte = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
            with urllib.request.urlopen(byte, timeout=10) as response:
                if response.status != 206 or len(response.read(2)) != 1:
                    raise SystemExit("Identity-bound byte-range delivery failed.")
    after = request_json(arguments.base_url, "/api/v1/processing/overview")
    fields = ("running_count", "queued_count", "failed_count", "succeeded_count")
    if any(before.get(field) != after.get(field) for field in fields):
        raise SystemExit("Smoke checks changed processing state unexpectedly.")
    print("Local liveness, readiness, saved catalog, and zero-implicit-work checks passed.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise SystemExit("The local smoke check failed safely.") from error
