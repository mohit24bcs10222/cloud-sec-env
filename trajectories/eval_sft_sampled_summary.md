## Qwen2.5-7B + SFT eval (vs deployed Space)

- Endpoint: `https://aw4s1abcrifynpw2.us-east-1.aws.endpoints.huggingface.cloud`
- Episodes: 5
- Submission rate: **40%** (2/5)
- Mean terminal reward (submitted only): **0.625**
- Mean total reward (all): **1.550**
- Mean steps per episode: 25.0

| # | submitted | terminal | total | steps | stop |
|---|---|---|---|---|---|
| 1 | NO | - | 1.300 | 26 | `parse_fail` |
| 2 | YES | 0.450 | 1.350 | 19 | `submit` |
| 3 | NO | - | 1.600 | 30 | `budget_exhausted` |
| 4 | YES | 0.800 | 1.500 | 20 | `submit` |
| 5 | NO | - | 2.000 | 30 | `budget_exhausted` |