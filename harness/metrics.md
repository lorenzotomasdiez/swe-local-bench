# Cross-runner metrics

1 instances, 4 runners.

Dropped, not attempted by every runner: 14692, 14694, 14702, 14730, 14744, 14746, 14747, 14752, 14753.

| Runner | Solve rate | TP | FP | FN | TN | Avg time | Avg cost | Total |
|---|---|---|---|---|---|---|---|---|
| pi-deepseek-v4-flash | - | 0 | 0 | 0 | 0 | - | - | - |
| claude-haiku | - | 0 | 0 | 0 | 0 | - | - | - |
| claude-sonnet | - | 0 | 0 | 0 | 0 | - | - | - |
| claude-opus | - | 0 | 0 | 0 | 0 | - | - | - |

TP passed tests and judged valid. FP passed tests but judged wrong. FN judged valid but failed tests. TN failed tests and judged wrong.

| PR | pi-deepseek-v4-flash | claude-haiku | claude-sonnet | claude-opus |
|---|---|---|---|---|
| 14760 | –  | –  | –  | –  |
