# Cloud Sec Env -- SFT training data

Opus-generated trajectories for fine-tuning a small LLM (Qwen2.5-7B) to investigate
cloud-security incidents in our [Cloud Sec Env](https://github.com/<TODO>).

Each row is one full trajectory (system prompt + alert + alternating tool calls and
results, ending with a `submit_answer` action). Assistant turns are pre-formatted as
JSON objects of the shape `{"reasoning", "tool_name", "arguments"}` so a fine-tune
on this data produces parseable JSON output end-to-end.

Filtered for `terminal_reward >= 0.5` under our deterministic keyword rubric.

## Load

```python
from datasets import load_dataset
ds = load_dataset("Krishna3451112/cloud-sec-env-sft", split="train")
```
