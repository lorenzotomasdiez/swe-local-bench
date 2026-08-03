# Cross-runner metrics

2 instances common to 2 runners.

Dropped, not attempted by every runner: 14466, 14493, 14752, 14753.

| Runner | Solve rate | TP | FP | FN | TN | Avg time | Avg cost | Total |
|---|---|---|---|---|---|---|---|---|
| claude-opus | 2/2 (100%) | 2 | 0 | 0 | 0 | 1.6m | - | - |
| pi-deepseek-v4-flash | 2/2 (100%) | 1 | 1 | 0 | 0 | 1.9m | $0.0121 | $0.02 |

TP passed tests and judged valid. FP passed tests but judged wrong. FN judged valid but failed tests. TN failed tests and judged wrong.

| PR | claude-opus | pi-deepseek-v4-flash |
|---|---|---|
| 14475 | ✅ TP | ✅ TP |
| 14760 | ✅ TP | ✅ FP |
