## AN2 alignment rubric (align_v5)

This rubric is an **auto-score** to help triage data quality. It is **not** canonical scholarship.

### Score dimensions (0–5 each; max 30)

- **source_ids_url**
  - 5 if `sc_id` exists, `sc_url` exists, and `sc_id` appears inside `sc_url` (case-insensitive).
  - 0 otherwise.

- **text_to_source**
  - Jaccard similarity between tokens from `sutta` and `sc_sutta`.
  - Tokens are normalized for scoring (lowercased, light filler removal) and **stopwords removed**.
  - Mapped into 0–5 by thresholds in `update_alignment_an2.py`.

- **audio_segment**
  - 5 if `aud_file` is non-empty and `aud_end_s > aud_start_s >= 0`.
  - 0 otherwise.

- **commentary**
  - Keyword-relatedness score:
    - primary: overlap of `commentary` with `chain.items`
    - secondary: overlap of `commentary` with `chain.items + sutta + sc_sutta`
  - The higher of the two similarities is mapped to 0–5.

- **chain**
  - Structural + support score:
    - `chain.count` must match `len(chain.items)` for full credit.
    - Each chain item is “supported” when ≥70% of its (normalized, stopword-stripped) tokens appear somewhere in `sutta + commentary + sc_sutta`.

- **boundaries**
  - Checks for obvious truncation / dangling tails in `sutta`.

### Review flag (`needs_review`)

Marked true when:
- source ID/URL linkage fails, or
- `text_to_source` is very low (0–1), or
- commentary looks unrelated (when commentary exists), or
- the total excluding commentary is below a safety floor.

