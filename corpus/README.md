# Corpus

Redistributable documents only. Each `manifest.jsonl` row: license-gated
(CC0 / CC-BY / CC-BY-SA / public-domain / own-consented), attribution required;
page-image bodies live in the `bestocr-corpus` HF dataset, this repo stores
hashes and metadata (see `SUBMISSION_FORMAT.md`).

The natural first inhabitant is the **human-annotated reference subset** that
bestOCR's assembly estimands (`quality.reading_order_tau@v1`,
`quality.table_structure_f1@v1`) are blocked on — building that subset and
populating this corpus are the same act of work (bestOCR #16 spec §12 ↔ #33).
