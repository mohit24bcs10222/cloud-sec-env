"""Clean the AutoTrain adapter (drop vocab-tied LoRA layers) and push to a new HF repo.

The AutoTrain run set `target_modules=all-linear` + `add_eos_token=True`, which
caused embed_tokens and lm_head to be saved at the tokenizer's actual vocab
size (151665) instead of the base model's padded size (152064). That breaks
loading on any standard Qwen2.5-7B base.

Fix: download the adapter, strip embed_tokens/lm_head LoRA weights from the
safetensors file, rewrite adapter_config.json with a clean target_modules
list, push as a new repo. The remaining LoRA layers (attention + MLP) carry
~95% of the SFT learning.

Usage:
    python scripts/clean_and_push_adapter.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

from huggingface_hub import HfApi, snapshot_download
from safetensors.torch import load_file, save_file


SOURCE_REPO = "Krishna3451112/cloud-sec"
TARGET_REPO = "Krishna3451112/cloud-sec-clean"
LOCAL_DIR = _PROJECT_ROOT / "build" / "cloud-sec-adapter-clean"


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN not set in .env or shell.", file=sys.stderr)
        return 1

    LOCAL_DIR.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Downloading adapter from {SOURCE_REPO} ...")
    snapshot_download(SOURCE_REPO, local_dir=str(LOCAL_DIR), token=token)

    sft_path = LOCAL_DIR / "adapter_model.safetensors"
    cfg_path = LOCAL_DIR / "adapter_config.json"

    print(f"[2/4] Stripping vocab-tied keys from safetensors ...")
    import gc
    import shutil
    state = load_file(str(sft_path))
    n_before = len(state)
    # .clone() detaches from the mmap so we can rewrite the file (Windows lock).
    filtered = {k: v.clone() for k, v in state.items() if "embed_tokens" not in k and "lm_head" not in k}
    n_after = len(filtered)
    dropped_keys = sorted(k for k in state.keys() if k not in filtered)
    print(f"  total: {n_before}  kept: {n_after}  dropped: {n_before - n_after}")
    for k in dropped_keys:
        v = state[k]
        size_mb = v.numel() * v.element_size() / 1024 / 1024
        print(f"    - {k:80s} {tuple(v.shape)}  {size_mb:.1f} MB")
    # Drop the mmap-backed dict and force GC before writing back.
    del state
    gc.collect()
    tmp_path = sft_path.with_suffix(".tmp.safetensors")
    save_file(filtered, str(tmp_path))
    del filtered
    gc.collect()
    sft_path.unlink()
    shutil.move(str(tmp_path), str(sft_path))

    new_size_mb = sft_path.stat().st_size / 1024 / 1024
    print(f"  rewrote adapter_model.safetensors ({new_size_mb:.1f} MB)")

    print(f"[3/4] Updating adapter_config.json ...")
    with open(cfg_path) as f:
        cfg = json.load(f)
    old_targets = cfg.get("target_modules")
    safe_targets = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    if old_targets == "all-linear":
        cfg["target_modules"] = safe_targets
    elif isinstance(old_targets, list):
        cfg["target_modules"] = [m for m in old_targets if m not in ("embed_tokens", "lm_head")] or safe_targets
    cfg["modules_to_save"] = None
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"  target_modules: {old_targets!r}  ->  {cfg['target_modules']!r}")
    print(f"  modules_to_save: {cfg.get('modules_to_save')}")

    print(f"[4/4] Pushing cleaned adapter to {TARGET_REPO} ...")
    api = HfApi(token=token)
    api.create_repo(repo_id=TARGET_REPO, exist_ok=True, private=False, repo_type="model")
    api.upload_folder(
        folder_path=str(LOCAL_DIR),
        repo_id=TARGET_REPO,
        repo_type="model",
        commit_message="Clean adapter: drop vocab-tied LoRA layers (embed_tokens, lm_head) for inference compatibility",
    )
    print(f"\nDONE. Cleaned adapter at https://huggingface.co/{TARGET_REPO}")
    print(f"Original: https://huggingface.co/{SOURCE_REPO} (kept untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
