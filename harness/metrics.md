# Cross-runner metrics

15 instances, 4 runners.

| Runner | Solve rate | TP | FP | FN | TN | Avg time | Avg cost | Total | $/win |
|---|---|---|---|---|---|---|---|---|---|
| pi-deepseek-v4-flash | 5/15 (33%) | 2 | 3 | 2 | 8 | 3.8m | $0.0322 | $0.48 | $0.24 |
| claude-haiku | 5/15 (33%) | 4 | 1 | 2 | 8 | 6.6m | $0.7730 | $11.59 | $2.90 |
| claude-sonnet | 10/15 (67%) | 10 | 0 | 3 | 2 | 2.6m | $0.7537 | $11.31 | $1.13 |
| claude-opus | 8/15 (53%) | 8 | 0 | 5 | 2 | 4.3m | $1.2559 | $18.84 | $2.35 |

TP passed tests and judged valid. FP passed tests but judged wrong. FN judged valid but failed tests. TN failed tests and judged wrong.

| PR | pi-deepseek-v4-flash | claude-haiku | claude-sonnet | claude-opus |
|---|---|---|---|---|
| 14622 | ❌ TN | ❌ TN | ✅ TP | ✅ TP |
| 14639 | ❌ TN | ✅ TP | ✅ TP | ✅ TP |
| 14645 | ❌ TN | ❌ TN | ✅ TP | ✅ TP |
| 14646 | ❌ TN | ❌ FN | ❌ TN | ❌ FN |
| 14661 | ❌ TN | ❌ TN | ❌ FN | ❌ FN |
| 14692 | ❌ TN | ✅ TP | ✅ TP | ❌ TN |
| 14694 | ❌ TN | ❌ TN | ✅ TP | ✅ TP |
| 14702 | ❌ FN | ❌ TN | ❌ TN | ❌ TN |
| 14730 | ✅ TP | ✅ TP | ✅ TP | ✅ TP |
| 14744 | ❌ TN | ❌ TN | ✅ TP | ✅ TP |
| 14746 | ✅ FP | ❌ TN | ✅ TP | ✅ TP |
| 14747 | ✅ FP | ❌ FN | ✅ TP | ❌ FN |
| 14752 | ✅ TP | ✅ TP | ✅ TP | ✅ TP |
| 14753 | ❌ FN | ❌ TN | ❌ FN | ❌ FN |
| 14760 | ✅ FP | ✅ FP | ❌ FN | ❌ FN |
