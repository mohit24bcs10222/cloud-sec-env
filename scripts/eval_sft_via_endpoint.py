"""Evaluate the SFT'd Qwen against the deployed PagerBench env using a HF Inference Endpoint as the LLM.

Drives the model entirely over HTTP -- no local GPU required. The HF endpoint
runs Qwen2.5-7B + our cleaned LoRA; we apply the chat template locally and POST
the rendered prompt at each turn.

Usage (after `.env` is filled with HF_TOKEN):
    python scripts/eval_sft_via_endpoint.py \\
        --endpoint https://<your-endpoint>.us-east-1.aws.endpoints.huggingface.cloud \\
        --n 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any

import requests
from dotenv import load_dotenv
from transformers import AutoTokenizer

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT))

# Reuse the EXACT system prompt our SFT data was rendered with -- ensures the
# trained model sees the same tool listings + format instructions.
from cloud_sec_env.agent.adapters.qwen_adapter import QWEN_SYSTEM_PROMPT


DEFAULT_ENV_BASE = "https://Krishna3451112-cloud-sec-env-space.hf.space"
DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"


# ---------------------------------------------------------------------------
# JSON extraction (mirrors QwenAdapter)
# ---------------------------------------------------------------------------

def extract_json(text: str | None) -> dict | None:
    """Tolerant JSON extractor for the SFT'd Qwen.

    The model sometimes emits literal ``\\n`` sequences between JSON fields
    (artifact of how trajectories were tokenised during SFT). Standard
    json.loads rejects ``\\n`` outside strings as invalid -- we strip them
    before parsing. We also tolerate ``\\t``. Newlines/tabs INSIDE strings
    get collapsed to spaces, which only affects human-readable reasoning
    text, never the tool_name / arguments fields.
    """
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    def _try_parse(s: str) -> dict | None:
        for candidate in (s, s.replace("\\n", " ").replace("\\t", " ")):
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
        return None

    obj = _try_parse(text)
    if obj is not None:
        return obj

    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                obj = _try_parse(text[start:i + 1])
                if obj is not None:
                    return obj
                return None
    return None


# ---------------------------------------------------------------------------
# Endpoint client
# ---------------------------------------------------------------------------

class EndpointLLM:
    def __init__(
        self,
        url: str,
        token: str,
        tokenizer: Any,
        max_new_tokens: int = 384,
        temperature: float = 0.0,
    ):
        """temperature == 0.0 -> greedy (do_sample=False). Otherwise sampled."""
        self.url = url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.tokenizer = tokenizer
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature

    def generate(self, messages: list[dict]) -> str:
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        params: dict[str, Any] = {
            "max_new_tokens": self.max_new_tokens,
            "return_full_text": False,
        }
        if self.temperature > 0.0:
            params.update({"do_sample": True, "temperature": self.temperature, "top_p": 0.95})
        else:
            params["do_sample"] = False
        payload = {"inputs": prompt, "parameters": params}
        r = requests.post(self.url, headers=self.headers, json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return data[0].get("generated_text", "")
        if isinstance(data, dict):
            return data.get("generated_text", "")
        return ""


# ---------------------------------------------------------------------------
# Episode driver
# ---------------------------------------------------------------------------

def run_episode(llm: EndpointLLM, env_base: str, max_steps: int = 30, verbose: bool = True) -> dict[str, Any]:
    obs = requests.post(f"{env_base}/reset", json={}, timeout=60).json()["observation"]
    messages = [
        {"role": "system", "content": QWEN_SYSTEM_PROMPT},
        {"role": "user", "content": obs["content"]},
    ]
    total_reward = 0.0
    terminal_reward: float | None = None
    submitted = False
    steps = 0
    stop_reason = "budget_exhausted"

    for step_i in range(max_steps):
        try:
            text = llm.generate(messages)
        except requests.HTTPError as e:
            stop_reason = f"endpoint_error:{e.response.status_code}"
            if verbose:
                print(f"  step {step_i + 1}: endpoint HTTP {e.response.status_code}")
            break
        except Exception as e:
            stop_reason = f"endpoint_error:{type(e).__name__}"
            if verbose:
                print(f"  step {step_i + 1}: endpoint exception {e}")
            break

        parsed = extract_json(text)
        messages.append({"role": "assistant", "content": text})
        if parsed is None or not isinstance(parsed.get("tool_name"), str):
            stop_reason = "parse_fail"
            if verbose:
                print(f"  step {step_i + 1}: PARSE FAIL.  raw text ({len(text)} chars):")
                print("    " + text.replace("\n", "\n    "))
            break

        action = {
            "tool_name": parsed["tool_name"],
            "arguments": parsed.get("arguments") or {},
            "reasoning": parsed.get("reasoning"),
        }
        try:
            r = requests.post(f"{env_base}/step", json={"action": action}, timeout=120).json()
        except Exception as e:
            stop_reason = f"env_error:{type(e).__name__}"
            if verbose:
                print(f"  step {step_i + 1}: env error {e}")
            break

        new_obs = r["observation"]
        reward = float(r.get("reward") or 0.0)
        total_reward += reward
        steps = step_i + 1

        if verbose:
            print(f"  step {steps:2d}: {action['tool_name']:14s} reward={reward:+.3f} done={r.get('done')}")

        messages.append({
            "role": "user",
            "content": f"[{new_obs['observation_type'].upper()}]\n{new_obs['content']}",
        })

        if r.get("done"):
            if action["tool_name"] == "submit_answer":
                terminal_reward = reward
                submitted = True
                stop_reason = "submit"
            else:
                stop_reason = f"done:{new_obs.get('observation_type')}"
            break

    return {
        "submitted": submitted,
        "terminal_reward": terminal_reward,
        "total_reward": round(total_reward, 4),
        "num_steps": steps,
        "stop_reason": stop_reason,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def render_markdown(endpoint_url: str, results: list[dict[str, Any]]) -> str:
    n = len(results)
    submitted = [r for r in results if r["submitted"]]
    submit_rate = 100.0 * len(submitted) / n if n else 0.0
    mean_terminal = mean([r["terminal_reward"] for r in submitted]) if submitted else 0.0
    mean_total = mean([r["total_reward"] for r in results]) if results else 0.0
    mean_steps = mean([r["num_steps"] for r in results]) if results else 0.0

    lines = [
        "## Qwen2.5-7B + SFT eval (vs deployed Space)",
        "",
        f"- Endpoint: `{endpoint_url}`",
        f"- Episodes: {n}",
        f"- Submission rate: **{100*len(submitted)/n:.0f}%** ({len(submitted)}/{n})",
        f"- Mean terminal reward (submitted only): **{mean_terminal:.3f}**",
        f"- Mean total reward (all): **{mean_total:.3f}**",
        f"- Mean steps per episode: {mean_steps:.1f}",
        "",
        "| # | submitted | terminal | total | steps | stop |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        term = f"{r['terminal_reward']:.3f}" if r["terminal_reward"] is not None else "-"
        lines.append(
            f"| {i} | {'YES' if r['submitted'] else 'NO'} | {term} | "
            f"{r['total_reward']:.3f} | {r['num_steps']} | `{r['stop_reason']}` |"
        )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", required=True, help="HF Inference Endpoint URL")
    p.add_argument("--env-base", default=DEFAULT_ENV_BASE)
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--max-steps", type=int, default=30)
    p.add_argument("--max-new-tokens", type=int, default=384)
    p.add_argument("--temperature", type=float, default=0.0,
                   help="0.0 = greedy. >0 enables sampling at that temperature.")
    p.add_argument("--out", default="trajectories/eval_sft_endpoint_summary.md")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN not set.", file=sys.stderr)
        return 1

    print(f"[eval] Loading tokenizer for {DEFAULT_BASE_MODEL} ...")
    tokenizer = AutoTokenizer.from_pretrained(DEFAULT_BASE_MODEL, token=token)

    print(f"[eval] Sanity-pinging endpoint ...")
    sanity = requests.post(
        args.endpoint,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"inputs": "Hello", "parameters": {"max_new_tokens": 4, "do_sample": False, "return_full_text": False}},
        timeout=60,
    )
    sanity.raise_for_status()
    print(f"[eval] Endpoint OK: {sanity.json()}")

    print(f"[eval] Sanity-pinging env Space ...")
    env_ping = requests.post(f"{args.env_base}/reset", json={}, timeout=60).json()
    print(f"[eval] Env OK: observation_type={env_ping['observation']['observation_type']}, "
          f"steps_remaining={env_ping['observation']['steps_remaining']}")

    llm = EndpointLLM(args.endpoint, token, tokenizer,
                      max_new_tokens=args.max_new_tokens,
                      temperature=args.temperature)
    print(f"[eval] decoding: {'greedy' if args.temperature == 0 else f'sampling temp={args.temperature}'}")

    results = []
    for i in range(args.n):
        print(f"\n--- Rollout {i+1}/{args.n} ---")
        t0 = time.monotonic()
        res = run_episode(llm, args.env_base, max_steps=args.max_steps, verbose=not args.quiet)
        res["duration_s"] = round(time.monotonic() - t0, 1)
        results.append(res)
        term = f"{res['terminal_reward']:.3f}" if res["terminal_reward"] is not None else "-"
        print(f"  -> submit={res['submitted']} terminal={term} total={res['total_reward']:.3f} "
              f"steps={res['num_steps']} stop={res['stop_reason']} ({res['duration_s']}s)")

    md = render_markdown(args.endpoint, results)
    print()
    print(md)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"\n[eval] saved -> {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
