"""Push all project artifacts to the deployed HF Space.

Mirrors the GitHub project layout to the Space so judges have one place
to evaluate everything: notebooks, charts, scripts, docs, eval results.

Excludes:
  - Large binary files (.mp4, .safetensors, .zip)
  - Node / Python build artifacts (node_modules, venv, build, __pycache__, egg-info)
  - Secrets (.env)
  - Already-deployed env package (cloud_sec_env/, plus the data/ task fixtures)
  - Personal notes (demo/my.txt)

Form requirement: "Please DO NOT include big video files in your environment
submission on HF Hub" -- so the demo .mp4 is excluded; link via YouTube instead.
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


IGNORE_PATTERNS = [
    # Large binaries (per form: no big video files on HF Hub)
    "*.mp4",
    "*.safetensors",
    "*.zip",
    "*.parquet",
    "*.pdf",
    # Node.js / Remotion build artifacts
    "demo/video/node_modules/**",
    "demo/video/out/**",
    # Python build artifacts
    "venv/**",
    "build/**",
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
    "*.egg-info/**",
    "**/*.egg-info/**",
    ".pytest_cache/**",
    ".coverage",
    "htmlcov/**",
    # Secrets
    ".env",
    ".env.*",
    "*.secret",
    # Git internals
    ".git/**",
    ".gitignore",
    ".gitattributes",
    # Already on the Space at root level (deployed via openenv push)
    "cloud_sec_env/**",
    # Task fixtures already on the Space at /data
    "data/task_01_oidc_rotation/**",
    # Local adapter dump from AutoTrain (the cleaned LoRA lives on a Hub model repo)
    "colab/cloud_sec_sft_adapter/**",
    # Don't overwrite the PagerBench landing README we already pushed
    "README.md",
    # Logs / outputs
    "*.log",
    "cloud_sec_env/outputs/**",
    # Personal notes
    "demo/my.txt",
]


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN not set in .env", file=sys.stderr)
        return 1

    api = HfApi(token=token)
    print(f"Uploading project tree from {_PROJECT_ROOT} -> {SPACE_REPO} (root)")
    print(f"  ignore_patterns: {len(IGNORE_PATTERNS)} entries")

    api.upload_folder(
        folder_path=str(_PROJECT_ROOT),
        path_in_repo="",
        repo_id=SPACE_REPO,
        repo_type="space",
        ignore_patterns=IGNORE_PATTERNS,
        commit_message=(
            "Add full project artifacts to Space "
            "(notebooks, demo charts, eval scripts, build journal). "
            "Judges can now evaluate everything in one place."
        ),
    )
    print(f"\nDone. Browse: https://huggingface.co/spaces/{SPACE_REPO}/tree/main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
