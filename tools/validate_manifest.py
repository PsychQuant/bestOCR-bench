#!/usr/bin/env python3
"""Mechanical corpus-manifest checks for bestOCR-bench CI (stdlib only).

Each corpus/manifest.jsonl row describes one redistributable document set
(page-image bodies live in the HF dataset; this repo stores hashes/metadata).

Hard checks (exit 1 on any failure):
  1. required keys: corpus_id, title, doc_type, pages, license, attribution,
     hf_path, sha256
  2. license in the allowed set (CC0 / CC-BY / CC-BY-SA / public-domain /
     own-consented); attribution non-empty
  3. corpus_id and sha256 are hex digests (64); pages a positive int
  4. corpus_id unique

What CI cannot check — and therefore does not pretend to: that the material is
actually redistributable under the claimed license. That is the human review
every corpus PR gets (SUBMISSION_FORMAT.md).
"""
import json
import re
import sys

REQUIRED = {"corpus_id", "title", "doc_type", "pages", "license",
            "attribution", "hf_path", "sha256"}
LICENSES = {"CC0", "CC-BY", "CC-BY-SA", "public-domain", "own-consented"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "corpus/manifest.jsonl"
    errors, ids = [], set()
    count = 0
    try:
        handle = open(path, encoding="utf-8")
    except FileNotFoundError:
        print(f"FAIL manifest not found: {path}")
        return 1
    with handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            count += 1
            where = f"manifest.jsonl:{lineno}"
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{where}: invalid JSON ({exc})")
                continue
            missing = REQUIRED - row.keys()
            if missing:
                errors.append(f"{where}: missing keys {sorted(missing)}")
                continue
            if row["license"] not in LICENSES:
                errors.append(f"{where}: license {row['license']!r} not in {sorted(LICENSES)}")
            if not str(row["attribution"]).strip():
                errors.append(f"{where}: attribution must be non-empty")
            for key in ("corpus_id", "sha256"):
                if not HEX64.match(str(row[key])):
                    errors.append(f"{where}: {key} must be a 64-char hex digest")
            if not (isinstance(row["pages"], int) and row["pages"] > 0):
                errors.append(f"{where}: pages must be a positive integer")
            if row["corpus_id"] in ids:
                errors.append(f"{where}: duplicate corpus_id {row['corpus_id']!r}")
            ids.add(row["corpus_id"])

    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print(f"ok: {count} manifest row(s) pass hard checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
