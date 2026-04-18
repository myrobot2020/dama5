Criteria — **prod-ready**: non-empty sutta & commentary; audio has `aud_file`, `aud_start_s`, `aud_end_s` with end ≥ start; **good chain**: `len(chain.items)==book` and every item non-empty.

Inference artifact: `C:\Users\ADMIN\Desktop\dama5\chains_infer_an4_11.jsonl` (per-file infer rows; prod-grade means infer filled all N slots).

```
| book | suttas | +sutta text | +commentary | +audio | +chain obj | good chains | prod-ready | parse err |
|-----:|-------:|------------:|------------:|-------:|-----------:|------------:|-----------:|----------:|
| 11 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 0 |
| 10 | 18 | 18 | 14 | 13 | 0 | 0 | 0 | 0 |
| 9 | 28 | 28 | 21 | 17 | 0 | 0 | 0 | 0 |
| 8 | 49 | 49 | 33 | 33 | 0 | 0 | 0 | 0 |
| 7 | 38 | 38 | 28 | 28 | 0 | 0 | 0 | 0 |
| 6 | 32 | 32 | 28 | 24 | 0 | 0 | 0 | 0 |
| 5 | 91 | 91 | 69 | 63 | 0 | 0 | 0 | 0 |
| 4 | 71 | 71 | 37 | 34 | 0 | 0 | 0 | 0 |
```
