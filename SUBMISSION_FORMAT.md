# Submission format

## Measurements

- **Filename**: `measurements/<UTC ISO-8601 basic, e.g. 20260730T093000Z>-<contributor>-<machine_id first 12>.jsonl`
  — one file per submission, **append-only** (PRs never modify existing files).
- **Each line** (JSONL) = a bestOCR `EvidenceRow`, snake_case, **plus 4
  submission fields** (denormalized so the file is self-sufficient):

```json
{"estimand": "speed.ms_per_page@v1", "value": 1981,
 "condition": {"model": "glm-ocr", "quant": "q8_0", "dpi": 150,
               "doc_type": "scanned_doc", "platform": "ollama",
               "hardware": "Apple M4 Max 128GB", "instrument": "bestocr 0.9.0",
               "tool_version": null},
 "tier": "T2-community", "source": "bench:self", "caveat": null,
 "contributor": "your-github-handle", "machine_id": "0f3a1b2c4d5e",
 "measured_at": "2026-07-30T09:30:00Z", "corpus_id": "<sha256 from corpus/manifest.jsonl>"}
```

Hard rules (CI fails the PR):

- `tier` MUST be `"T2-community"` — this repo mints no other provenance.
- `estimand` MUST be a versioned name from the schema vocabulary
  (`schema/evidence-schema.md` §2) or a `consensus.<adjudicator>.<quantity>@vN`
  name with a known adjudicator segment. Unknown estimands are rejected, not
  admitted — hard rule 2 enforced at the gate.
- `value` ranges per estimand family: `speed.*` > 0 (milliseconds);
  `quality.*recall*` / `*_f1` / `*share` / `*accuracy*` ∈ [0, 1];
  `*reading_order_tau*` ∈ [−1, 1].
- `corpus_id` MUST exist in `corpus/manifest.jsonl` — only measurements against
  the canonical corpus are comparable.
- No bitwise-duplicate rows repo-wide.
- `condition` MUST carry the full tuple (`model`, `quant`, `doc_type`,
  `platform`, `hardware`, `instrument`; `dpi` and `tool_version` nullable).
  `triage.*` estimands additionally REQUIRE `triage_text_min` and
  `triage_frag_max` — the effective thresholds that produced the routing
  verdicts (schema §3): rows measured under different thresholds are different
  conditions and must never share a grouping key.

Soft flags (never fail CI — printed for human review):

- `condition.platform == "python"` (adapter-backed engine) with
  `tool_version` null → **warned**: rows across a tool upgrade are otherwise
  indistinguishable (bestOCR #28).
- A row whose `value` deviates from the median of its
  (`estimand`, `condition.model`, `condition.doc_type`, `corpus_id`) group by
  more than 3×MAD → `⚠ outlier`, transparency over pretended verification.

## Corpus manifest

`corpus/manifest.jsonl`, one JSON object per line:

```json
{"corpus_id": "<sha256 of the page-image set>", "title": "…",
 "doc_type": "scanned_doc", "pages": 12,
 "license": "CC-BY", "attribution": "…",
 "hf_path": "datasets/PsychQuant/bestocr-corpus/…", "sha256": "<archive sha256>"}
```

- `license` ∈ {CC0, CC-BY, CC-BY-SA, public-domain, own-consented};
  `attribution` required. Page-image bodies live in the HF dataset; this repo
  stores hashes and metadata only.
- Corpus PRs get mechanical CI **plus human review** (license verification and
  reference-annotation quality) — the redistributability rule is enforced by
  people, because CI cannot inspect provenance.
