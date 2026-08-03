#!/usr/bin/env python3
"""Mechanical measurement checks for bestOCR-bench CI (stdlib only).

Validates every measurements/*.jsonl row against the contract in
SUBMISSION_FORMAT.md — which is bestOCR's EvidenceRow (estimand x condition
tuple x provenance tier, schema/evidence-schema.md) plus submission fields.

Hard checks (exit 1 on any failure):
  1. filename convention: <UTC-basic>Z-<contributor>-<machine12>.jsonl
  2. required keys present; condition carries the full tuple
  3. tier == "T2-community" — this repo mints no other provenance
  4. estimand in the schema vocabulary (versioned), or a
     consensus.<known-adjudicator>.<quantity>@vN name (hard rule 2 at the gate)
  5. value ranges per estimand family
  6. corpus_id exists in corpus/manifest.jsonl
  7. no bitwise-duplicate rows repo-wide
  8. measured_at is ISO-8601 UTC (Z)

Soft flags (printed, never fail CI — transparency over pretended verification):
  - adapter-backed row (condition.platform == "python") with null
    tool_version -> warn (bestOCR #28: rows across a tool upgrade are
    otherwise indistinguishable)
  - value deviating from the median of its (estimand, model, doc_type,
    corpus_id) group by > 3x MAD -> "outlier" for human review

Vocabulary note: EST_VOCAB / ADJUDICATOR_SEGMENTS mirror the vendored schema
(schema/evidence-schema.md §2) and bestOCR's AdjudicatorRegistry. When the
canonical schema adds an estimand, sync BOTH the vendored copy and this list —
CI failing on a legitimately new estimand is the reminder, not a bug.
"""
import glob
import json
import math
import os
import re
import statistics
import sys

EST_VOCAB = {
    "speed.ms_per_page@v1",
    "speed.ensemble_ms_per_page@v1",
    "quality.word_recall@v1",
    "quality.token_recall_vs_cloud@v1",
    "quality.reading_order_tau@v1",
    "quality.table_structure_f1@v1",
    "triage.route_accuracy@v1",
}
ADJUDICATOR_SEGMENTS = {"ds_lite", "majority", "ds_full", "prior_weighted", "irt", "rover"}
CONSENSUS_RE = re.compile(r"^consensus\.([a-z0-9_]+)\.([a-z0-9_]+)@v\d+$")

REQUIRED = {"estimand", "value", "condition", "tier", "source",
            "contributor", "machine_id", "measured_at", "corpus_id"}
CONDITION_REQUIRED = {"model", "quant", "doc_type", "platform", "hardware", "instrument"}
# Per-estimand extras (schema §3): triage rows are a function of two env-overridable
# thresholds — without them in the condition, rows measured under different
# thresholds are indistinguishable and any aggregation is cross-condition (DA-1).
TRIAGE_CONDITION_REQUIRED = {"triage_text_min", "triage_frag_max"}
FILENAME_RE = re.compile(r"^\d{8}T\d{6}Z-[A-Za-z0-9-]+-[0-9a-f]{12}\.jsonl$")
MEASURED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def estimand_ok(name):
    if name in EST_VOCAB:
        return True
    match = CONSENSUS_RE.match(name)
    return bool(match and match.group(1) in ADJUDICATOR_SEGMENTS)


def value_range_error(estimand, value):
    """Range per estimand family; None when in range."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "value is not numeric"
    if estimand.startswith("speed."):
        if value <= 0:
            return "speed values are positive milliseconds"
    elif "reading_order_tau" in estimand:
        if not -1.0 <= value <= 1.0:
            return "tau must be in [-1, 1]"
    elif any(token in estimand for token in ("recall", "_f1", "share", "accuracy")):
        if not 0.0 <= value <= 1.0:
            return "recall/f1/share/accuracy must be in [0, 1]"
    return None


def load_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if line:
                yield lineno, line


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    corpus_ids = set()
    manifest = os.path.join(repo, "corpus", "manifest.jsonl")
    if os.path.exists(manifest):
        for _, line in load_jsonl(manifest):
            try:
                corpus_ids.add(json.loads(line)["corpus_id"])
            except (json.JSONDecodeError, KeyError):
                pass  # validate_manifest.py owns manifest errors

    errors, seen, groups = [], {}, {}
    files = sorted(glob.glob(os.path.join(repo, "measurements", "*.jsonl")))
    for path in files:
        name = os.path.basename(path)
        if not FILENAME_RE.match(name):
            errors.append(f"{name}: filename does not match "
                          "<UTC-basic>Z-<contributor>-<machine12>.jsonl")
        for lineno, line in load_jsonl(path):
            where = f"{name}:{lineno}"
            if line in seen:
                errors.append(f"{where}: bitwise-duplicate of {seen[line]}")
                continue
            seen[line] = where
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{where}: invalid JSON ({exc})")
                continue

            missing = REQUIRED - row.keys()
            if missing:
                errors.append(f"{where}: missing keys {sorted(missing)}")
                continue
            condition = row["condition"]
            if not isinstance(condition, dict):
                errors.append(f"{where}: condition is not an object")
                continue
            cond_missing = CONDITION_REQUIRED - condition.keys()
            row_error_start = len(errors)   # any error on this row excludes it from grouping (verify R3)
            if row.get("estimand", "").startswith("triage."):
                cond_missing |= TRIAGE_CONDITION_REQUIRED - condition.keys()
                # Presence is not enough (verify R2): null / bool / non-numeric /
                # out-of-domain thresholds would silently re-merge different
                # conditions (None == None) or crash grouping (unhashable list).
                # Finite-only (verify R3): json.load turns 1e309 into float("inf"),
                # which passes `> 0` — finiteness is checked on floats only (calling
                # math.isfinite on an arbitrarily large int would overflow to C double).
                def _domain_number(v):
                    if isinstance(v, bool) or not isinstance(v, (int, float)):
                        return False
                    return not (isinstance(v, float) and not math.isfinite(v))
                for k, ok_domain, domain_desc in (
                    ("triage_text_min", lambda v: v > 0, "a finite number > 0"),
                    ("triage_frag_max", lambda v: 0 < v <= 1, "a number in (0, 1]"),
                ):
                    if k not in condition:
                        continue   # absence already reported via cond_missing
                    v = condition[k]
                    if not _domain_number(v) or not ok_domain(v):
                        errors.append(f"{where}: {k} must be {domain_desc} (got {v!r})")
            elif TRIAGE_CONDITION_REQUIRED & condition.keys():
                # schema §3: non-triage rows omit both keys — carrying them would
                # split soft-outlier groups that should be one (verify R2).
                errors.append(f"{where}: {sorted(TRIAGE_CONDITION_REQUIRED & condition.keys())} "
                              "are only valid on triage.* rows (schema §3: non-triage rows omit both)")
            if cond_missing:
                errors.append(f"{where}: condition missing {sorted(cond_missing)}")
            if row["tier"] != "T2-community":
                errors.append(f"{where}: tier must be \"T2-community\" "
                              f"(got {row['tier']!r}) — this repo mints no other provenance")
            if not estimand_ok(row["estimand"]):
                errors.append(f"{where}: unknown estimand {row['estimand']!r} — "
                              "hard rule 2: unknown names are rejected, not admitted")
            else:
                range_error = value_range_error(row["estimand"], row["value"])
                if range_error:
                    errors.append(f"{where}: {range_error} (got {row['value']!r})")
            if row["corpus_id"] not in corpus_ids:
                errors.append(f"{where}: corpus_id {row['corpus_id']!r} not in corpus/manifest.jsonl")
            if not MEASURED_AT_RE.match(str(row["measured_at"])):
                errors.append(f"{where}: measured_at must be ISO-8601 UTC (…Z)")

            if condition.get("platform") == "python" and condition.get("tool_version") is None:
                print(f"warn {where}: adapter-backed row without tool_version — "
                      "rows across a tool upgrade are indistinguishable (bestOCR #28)")

            # Whole-row error state gates grouping (verify R3): a row that failed ANY
            # hard check must not shape the soft-outlier statistics — key construction
            # lives inside the guard so unhashable defective values can never reach it.
            if len(errors) == row_error_start \
                    and isinstance(row["value"], (int, float)) and not isinstance(row["value"], bool):
                key = (row["estimand"], condition.get("model"),
                       condition.get("doc_type"), row["corpus_id"],
                       # triage grouping must never pool across thresholds (schema §3 / DA-1)
                       condition.get("triage_text_min"), condition.get("triage_frag_max"))
                groups.setdefault(key, []).append((where, float(row["value"])))

    # Soft outlier flags — never fail CI.
    for key, rows in groups.items():
        if len(rows) < 3:
            continue
        values = [value for _, value in rows]
        median = statistics.median(values)
        mad = statistics.median(abs(value - median) for value in values)
        if mad == 0:
            continue
        for where, value in rows:
            if abs(value - median) > 3 * mad:
                print(f"outlier {where}: value {value} deviates >3xMAD from "
                      f"median {median} of group {key} — for human review")

    if errors:
        for error in errors:
            print(f"FAIL {error}")
        print(f"{len(errors)} hard error(s) across {len(files)} file(s)")
        return 1
    print(f"ok: {len(seen)} row(s) across {len(files)} file(s) pass hard checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
