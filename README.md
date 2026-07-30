# bestOCR-bench

Public, cross-machine evidence layer for [bestOCR](https://github.com/PsychQuant/bestOCR)
— the OCR sibling of [bestASR-bench](https://github.com/PsychQuant/bestASR-bench),
with the same division of labor:

> **bestOCR keeps the instrument and the local evidence loop; this repo takes
> public aggregation.** Corpus, community-submitted measurements, leaderboard,
> submission format, and validation CI live here. Nothing in bestOCR's local
> loop (`run` → runlog → `evidence ingest` → T2 rows → `recommend`) changes.

Design: [`bestOCR/docs/superpowers/specs/2026-07-30-bestocr-bench.md`](https://github.com/PsychQuant/bestOCR/blob/main/docs/superpowers/specs/2026-07-30-bestocr-bench.md) (#33).

## How to submit a measurement

1. Run bestOCR (a released, version-named build) against a corpus entry listed
   in `corpus/manifest.jsonl`.
2. Promote the run through `bestocr evidence ingest <run-id>` — the row shape
   this repo accepts **is** bestOCR's `EvidenceRow`, snake_case, plus
   submission fields. See [`SUBMISSION_FORMAT.md`](SUBMISSION_FORMAT.md).
3. Open a PR adding **one new file** under `measurements/` (append-only — PRs
   must not modify existing files). CI validates mechanically; a human reviews.

## Provenance, stated up front

Rows here carry tier **`T2-community`**: measured by the released instrument on
hardware the maintainers do not control, attested by the contributor. That is a
*distinct label* from bestOCR's own `T2` ("our hardware, our instrument") and
from `T3` (vendor self-reported) — the leaderboard ranks **within
`T2-community` only**, and bestOCR's `recommend` does not consume these rows.
The three-label discipline (estimand × condition tuple × provenance tier) is
the contract in [`schema/evidence-schema.md`](schema/evidence-schema.md); its
canonical home is the bestOCR repo.

## Corpus

`corpus/manifest.jsonl` lists redistributable documents only — license ∈
{CC0, CC-BY, CC-BY-SA, public-domain, own-consented}, attribution required.
Page-image bodies live in the `bestocr-corpus` HF dataset; this repo stores
hashes and metadata. Third-party material that cannot be redistributed is
excluded **by rule** (CI cannot see what it cannot check — human review
enforces this).
