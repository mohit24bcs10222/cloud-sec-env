# Rubric ablation

Same agent answers, scored under three reward configurations. Demonstrates why we ship keyword-rubric as primary: it agrees with the LLM judge on most trajectories while requiring no API key.

## Aggregate

- Trajectories scored: **62**
- Mean keyword score:    **0.899**

## Per-trajectory

| trajectory | model | keyword | judge | composite | dims hit | steps |
|---|---|---|---|---|---|---|
| `task_01_oidc_rotation_claude-opus-4-5_20260425_030118_r1.json` | claude-opus-4-5 | 0.750 | - | - | 5/6 | 21 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_030118_r2.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 22 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_030118_r3.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 21 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_030118_r4.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 18 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_030118_r5.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 18 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_032832_r1.json` | claude-opus-4-5 | 0.700 | - | - | 4/6 | 21 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_032832_r2.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 22 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_032832_r3.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 20 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_032832_r4.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 21 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_032832_r5.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 23 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_043338_r1.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 23 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_043338_r2.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 22 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_043338_r3.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 22 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_043338_r4.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 21 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_043338_r5.json` | claude-opus-4-5 | 0.750 | - | - | 5/6 | 24 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_071202_r1.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 22 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_071202_r2.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 21 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_071202_r3.json` | claude-opus-4-5 | 0.700 | - | - | 4/6 | 23 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_071202_r4.json` | claude-opus-4-5 | 0.900 | - | - | 5/6 | 19 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_071202_r5.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 23 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_114734_r1.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 26 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_114734_r2.json` | claude-opus-4-5 | 0.900 | - | - | 5/6 | 29 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_114734_r3.json` | claude-opus-4-5 | 0.850 | - | - | 5/6 | 24 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_114734_r4.json` | claude-opus-4-5 | 0.850 | - | - | 5/6 | 27 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_114734_r5.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 26 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_120140_r1.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 25 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_120140_r2.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 30 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_120140_r3.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 21 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_120140_r4.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 29 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_120140_r5.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 25 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_121609_r1.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 25 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_121609_r2.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 29 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_121609_r3.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 25 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_121609_r4.json` | claude-opus-4-5 | 0.850 | - | - | 5/6 | 27 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_121609_r5.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 27 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r1.json` | claude-opus-4-5 | 0.750 | - | - | 4/6 | 26 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r10.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 26 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r12.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 23 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r13.json` | claude-opus-4-5 | 0.900 | - | - | 5/6 | 26 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r14.json` | claude-opus-4-5 | 0.550 | - | - | 4/6 | 30 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r16.json` | claude-opus-4-5 | 0.900 | - | - | 5/6 | 29 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r17.json` | claude-opus-4-5 | 0.850 | - | - | 5/6 | 30 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r18.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 25 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r19.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 27 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r20.json` | claude-opus-4-5 | 0.900 | - | - | 5/6 | 23 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r21.json` | claude-opus-4-5 | 0.900 | - | - | 5/6 | 30 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r24.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 28 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r25.json` | claude-opus-4-5 | 0.900 | - | - | 5/6 | 29 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r26.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 27 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r27.json` | claude-opus-4-5 | 0.900 | - | - | 5/6 | 30 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r28.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 22 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r29.json` | claude-opus-4-5 | 0.850 | - | - | 5/6 | 29 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r3.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 27 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r30.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 30 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r4.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 26 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r5.json` | claude-opus-4-5 | 1.000 | - | - | 6/6 | 26 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r6.json` | claude-opus-4-5 | 0.900 | - | - | 5/6 | 27 |
| `task_01_oidc_rotation_claude-opus-4-5_20260425_160235_r8.json` | claude-opus-4-5 | 0.750 | - | - | 4/6 | 25 |
| `task_01_oidc_rotation_claude-opus-4-7_20260424_172326_r1.json` | claude-opus-4-7 | 1.000 | - | - | 6/6 | 20 |
| `task_01_oidc_rotation_Qwen__Qwen2.5-7B-Instruct_20260425_155022_r2.json` | Qwen/Qwen2.5-7B-Instruct | 0.250 | - | - | 2/6 | 10 |
| `task_01_oidc_rotation_Qwen__Qwen2.5-7B-Instruct_20260425_155022_r3.json` | Qwen/Qwen2.5-7B-Instruct | 0.100 | - | - | 1/6 | 5 |
| `task_01_oidc_rotation_Qwen__Qwen2.5-7B-Instruct_20260425_155656_r5.json` | Qwen/Qwen2.5-7B-Instruct | 0.100 | - | - | 1/6 | 11 |

_Skipped 22 trajectories without submit_answer, 0 with parse errors._