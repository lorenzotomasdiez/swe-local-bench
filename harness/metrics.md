# Cross-runner metrics

2 instances, 4 runners.

| Runner | Solve rate | TP | FP | FN | TN | Avg time | Avg cost | Total | $/win |
|---|---|---|---|---|---|---|---|---|---|
| pi-deepseek-v4-flash | 1/2 (50%) | 0 | 1 | 1 | 0 | 10.3m | $0.1525 | $0.31 | - |
| claude-haiku | 0/2 (0%) | 0 | 0 | 1 | 1 | 5.4m | $0.6626 | $1.33 | - |
| claude-sonnet | 0/2 (0%) | 0 | 0 | 2 | 0 | 1.7m | $0.5770 | $1.15 | - |
| claude-opus | 0/2 (0%) | 0 | 0 | 2 | 0 | 3.7m | $0.9861 | $1.97 | - |

TP passed tests and judged valid. FP passed tests but judged wrong. FN judged valid but failed tests. TN failed tests and judged wrong.

| PR | pi-deepseek-v4-flash | claude-haiku | claude-sonnet | claude-opus |
|---|---|---|---|---|
| 14753 | ❌ FN | ❌ FN | ❌ FN | ❌ FN |
| 14760 | ✅ FP | ❌ TN | ❌ FN | ❌ FN |
