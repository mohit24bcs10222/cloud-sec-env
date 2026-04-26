"""Push the PagerBench incident workbench UI to the deployed HF Space.

Targeted upload: only the files needed for the new dark-themed workbench
to take effect on the live Space.

Files uploaded:
  - server/app.py (with /ui/config + static mounting)
  - server/static/index.html
  - server/static/styles.css
  - server/static/app.js

The Space root corresponds to the env package root (the `cloud_sec_env`
folder locally is unpacked at root inside the Space, so `cloud_sec_env/server/`
maps to `server/` on the Space).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

SPACE_REPO = "Krishna3451112/cloud-sec-env-space"
LOCAL_PKG = _PROJECT_ROOT / "cloud_sec_env"

# (local_path, path_in_space) tuples
UPLOADS: list[tuple[Path, str]] = [
    (LOCAL_PKG / "server" / "app.py", "server/app.py"),
    (LOCAL_PKG / "server" / "static" / "index.html", "server/static/index.html"),
    (LOCAL_PKG / "server" / "static" / "styles.css", "server/static/styles.css"),
    (LOCAL_PKG / "server" / "static" / "app.js", "server/static/app.js"),
]


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN not set in .env", file=sys.stderr)
        return 1

    api = HfApi(token=token)

    # Validate locally first.
    for src, _dst in UPLOADS:
        if not src.exists():
            print(f"ERROR: {src} not found", file=sys.stderr)
            return 1

    print(f"Pushing PagerBench workbench UI -> {SPACE_REPO}")
    for src, dst in UPLOADS:
        size = src.stat().st_size
        print(f"  {src.relative_to(_PROJECT_ROOT)} -> {dst} ({size} bytes)")
        api.upload_file(
            path_or_fileobj=str(src),
            path_in_repo=dst,
            repo_id=SPACE_REPO,
            repo_type="space",
            commit_message=f"workbench UI: {dst}",
        )

    print(f"\nDone. Space URL: https://huggingface.co/spaces/{SPACE_REPO}")
    print("HF Space will rebuild Docker image automatically (~1-3 min).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
