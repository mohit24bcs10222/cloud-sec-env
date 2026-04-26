"""Upload our SFT JSONL to HuggingFace Hub as a dataset.

Once uploaded, the Colab notebook can load it via:
    from datasets import load_dataset
    ds = load_dataset("<username>/cloud-sec-env-sft", split="train")

Usage:
    python scripts/upload_sft_to_hf.py \\
        --jsonl data/sft/cloud_sec_train.jsonl \\
        --repo-id <username>/cloud-sec-env-sft \\
        [--private]

Reads HF_TOKEN from .env (already configured in this project).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make sibling package importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", default="data/sft/cloud_sec_train.jsonl", help="Path to SFT JSONL")
    parser.add_argument("--repo-id", required=True, help="HF repo id, e.g. yourname/cloud-sec-env-sft")
    parser.add_argument("--private", action="store_true", help="Upload as private dataset")
    args = parser.parse_args()

    if not os.environ.get("HF_TOKEN"):
        print("ERROR: HF_TOKEN not set. Add it to .env.", file=sys.stderr)
        return 1

    src = Path(args.jsonl)
    if not src.exists():
        print(f"ERROR: {src} does not exist. Run scripts/build_sft_dataset.py first.", file=sys.stderr)
        return 1

    from huggingface_hub import HfApi, create_repo, upload_file

    api = HfApi(token=os.environ["HF_TOKEN"])

    # Create the dataset repo if it doesn't exist.
    try:
        create_repo(args.repo_id, repo_type="dataset", private=args.private, token=os.environ["HF_TOKEN"], exist_ok=True)
        print(f"Repo ready: {args.repo_id}")
    except Exception as e:
        print(f"Repo create warning: {e}", file=sys.stderr)

    # Upload the JSONL itself.
    upload_file(
        path_or_fileobj=str(src),
        path_in_repo="train.jsonl",
        repo_id=args.repo_id,
        repo_type="dataset",
        token=os.environ["HF_TOKEN"],
    )
    print(f"Uploaded {src} -> {args.repo_id}/train.jsonl")

    # Also upload a small README.
    readme = f"""# PagerBench -- SFT training data

Opus-generated trajectories for fine-tuning a small LLM (Qwen2.5-7B) to investigate
cloud-security incidents in our [PagerBench](https://github.com/<TODO>).

Each row is one full trajectory (system prompt + alert + alternating tool calls and
results, ending with a `submit_answer` action). Assistant turns are pre-formatted as
JSON objects of the shape `{{"reasoning", "tool_name", "arguments"}}` so a fine-tune
on this data produces parseable JSON output end-to-end.

Filtered for `terminal_reward >= 0.5` under our deterministic keyword rubric.

## Load

```python
from datasets import load_dataset
ds = load_dataset("{args.repo_id}", split="train")
```
"""
    readme_path = src.parent / "README.md"
    readme_path.write_text(readme, encoding="utf-8")
    upload_file(
        path_or_fileobj=str(readme_path),
        path_in_repo="README.md",
        repo_id=args.repo_id,
        repo_type="dataset",
        token=os.environ["HF_TOKEN"],
    )
    print(f"Uploaded README -> {args.repo_id}/README.md")

    print(f"\nDataset URL: https://huggingface.co/datasets/{args.repo_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
