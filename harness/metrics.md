# Cross-runner metrics

10 instances, 4 runners.

| Runner | Solve rate | TP | FP | FN | TN | Avg time | Avg cost | Total | $/win |
|---|---|---|---|---|---|---|---|---|---|
| claude-haiku | 4/10 (40%) | 3 | 1 | 1 | 5 | 4.9m | $0.5987 | $5.99 | $2.00 |
| claude-opus | 6/10 (60%) | 5 | 1 | 3 | 1 | 4.0m | $1.2829 | $12.83 | $2.57 |
| claude-sonnet | 7/10 (70%) | 6 | 1 | 1 | 2 | 3.6m | $1.1714 | $11.71 | $1.95 |
| pi-deepseek-v4-flash | 7/10 (70%) | 4 | 3 | 1 | 2 | 7.3m | $0.0606 | $0.55 | $0.14 |

TP passed tests and judged valid. FP passed tests but judged wrong. FN judged valid but failed tests. TN failed tests and judged wrong.

| PR | claude-haiku | claude-opus | claude-sonnet | pi-deepseek-v4-flash |
|---|---|---|---|---|
| 14692 | ❌ TN | ❌ TN | ✅ TP | ✅ TP |
| 14694 | ❌ TN | ✅ TP | ✅ TP | ❌ TN |
| 14702 | ❌ TN | ❌ FN | ❌ TN | ❌ TN |
| 14730 | ✅ TP | ✅ TP | ✅ TP | ✅ TP |
| 14744 | ❌ FN | ✅ TP | ✅ TP | ✅ TP |
| 14746 | ❌ TN | ✅ FP | ✅ FP | ✅ FP |
| 14747 | ✅ TP | ✅ TP | ✅ TP | ✅ FP |
| 14752 | ✅ TP | ✅ TP | ✅ TP | ✅ TP |
| 14753 | ❌ TN | ❌ FN | ❌ FN | ❌ FN |
| 14760 | ✅ FP | ❌ FN | ❌ TN | ✅ FP |
