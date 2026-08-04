# Cross-runner metrics

10 instances, 1 runner.

| Runner | Solve rate | TP | FP | FN | TN | Avg time | Avg cost | Total |
|---|---|---|---|---|---|---|---|---|
| pi-deepseek-v4-flash | 4/9 (44%) | 2 | 2 | 1 | 4 | 6.1m | $0.0725 | $0.65 |

TP passed tests and judged valid. FP passed tests but judged wrong. FN judged valid but failed tests. TN failed tests and judged wrong.

| PR | pi-deepseek-v4-flash |
|---|---|
| 14692 | ❌ TN |
| 14694 | –  |
| 14702 | ❌ TN |
| 14730 | ✅ TP |
| 14744 | ❌ TN |
| 14746 | ✅ FP |
| 14747 | ✅ FP |
| 14752 | ✅ TP |
| 14753 | ❌ FN |
| 14760 | ❌ TN |
