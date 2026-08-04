#!/usr/bin/env python3
"""Self-test for tools/validate_measurements.py — the submission CI gate.

Zero dependencies (stdlib only). Each case builds a throwaway fixture repo
(corpus manifest + measurement rows) in a tempdir, runs the validator as a
subprocess, and asserts on exit code + anchored output pattern + no-traceback (the traceback check runs for every case, known-gap pins included).
Fixtures are programmatic, not checked-in files.

Coverage claim (deliberately narrow): this suite fossilizes the #1 R1–R4
verify assertions and the #2 checklist items — symmetric per-threshold
type/domain/finiteness cases, per-direction value-range cases, and the row
structure defects that actually occurred. It does NOT claim one case per
vocabulary entry or per required key; single representatives stand in where
the validator handles members uniformly (set membership, key-set difference).
Run: python3 tools/tests/test_validate_measurements.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VALIDATOR = os.path.join(REPO_ROOT, "tools", "validate_measurements.py")

CORPUS_ID = "selftest-corpus-001"
FNAME = "20260804T000000Z-selftest-0123456789ab.jsonl"

# DELETE removes a key from the built condition; _UNSET distinguishes
# "no condition override supplied" from an explicit condition value, so a
# future case CAN set condition to null/non-dict without being silently
# swallowed (codex R1 finding).
DELETE = object()
_UNSET = object()


def base_row(**overrides):
    """A row that passes every hard check; overrides shape each case.

    `condition=<dict>` MERGES into the valid condition (DELETE removes keys);
    any other explicit condition value replaces it verbatim.
    """
    row = {
        "estimand": "triage.route_accuracy@v1",
        "value": 0.9,
        "condition": {
            "model": "n/a", "quant": "n/a", "doc_type": "scanned_doc",
            "platform": "macos", "hardware": "selftest", "instrument": "bestocr 0.10.0",
            "triage_text_min": 200, "triage_frag_max": 0.6,
        },
        "tier": "T2-community", "source": "selftest", "contributor": "selftest",
        "machine_id": "selftest", "measured_at": "2026-08-04T00:00:00Z",
        "corpus_id": CORPUS_ID,
    }
    condition_override = overrides.pop("condition", _UNSET)
    row.update(overrides)
    if isinstance(condition_override, dict):
        merged = {**row["condition"], **condition_override}
        row["condition"] = {k: v for k, v in merged.items() if v is not DELETE}
    elif condition_override is not _UNSET:
        row["condition"] = condition_override
    return row


def speed_row(**overrides):
    """Valid speed row; same merge semantics for `condition` as base_row."""
    condition_override = overrides.pop("condition", _UNSET)
    row = base_row(estimand="speed.ms_per_page@v1", value=850.5)
    row["condition"] = {k: v for k, v in row["condition"].items()
                       if not k.startswith("triage_")}
    row.update(overrides)
    if isinstance(condition_override, dict):
        merged = {**row["condition"], **condition_override}
        row["condition"] = {k: v for k, v in merged.items() if v is not DELETE}
    elif condition_override is not _UNSET:
        row["condition"] = condition_override
    return row


def raw_row(row, **field_literals):
    """Serialize a row but splice literal JSON tokens for given fields —
    for lexical paths json.dumps cannot produce (e.g. the literal `1e309`,
    which dumps as the non-standard `Infinity` token instead)."""
    text = json.dumps(row, ensure_ascii=False)
    for field, literal in field_literals.items():
        text = re.sub(r'("%s":\s*)("[^"]*"|[^,}\]]+)' % re.escape(field),
                      r"\g<1>%s" % literal, text, count=1)
    return text


def run_validator(rows=None, filename=FNAME, raw_lines=None):
    fixture = tempfile.mkdtemp(prefix="bench-selftest-")
    try:
        os.makedirs(os.path.join(fixture, "measurements"))
        os.makedirs(os.path.join(fixture, "corpus"))
        with open(os.path.join(fixture, "corpus", "manifest.jsonl"), "w") as f:
            f.write(json.dumps({"corpus_id": CORPUS_ID}) + "\n")
        with open(os.path.join(fixture, "measurements", filename), "w") as f:
            if raw_lines is not None:
                f.write("\n".join(raw_lines) + "\n")
            else:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        proc = subprocess.run([sys.executable, VALIDATOR, fixture],
                              capture_output=True, text=True, timeout=60)
        return proc.returncode, proc.stdout + proc.stderr
    finally:
        shutil.rmtree(fixture, ignore_errors=True)


def case(name, expect_ok, pattern, rows=None, filename=FNAME, raw_lines=None):
    return {"name": name, "rows": rows, "expect_ok": expect_ok,
            "pattern": pattern, "filename": filename, "raw_lines": raw_lines}


CASES = [
    # ── Happy paths ──────────────────────────────────────────────────────
    case("valid triage row passes", True, r"pass hard checks", [base_row()]),
    case("valid speed row passes (no thresholds required)", True, r"pass hard checks",
         [speed_row()]),
    case("accuracy boundary 0 accepted", True, r"pass hard checks", [base_row(value=0)]),
    case("accuracy boundary 1 accepted", True, r"pass hard checks", [base_row(value=1)]),

    # ── Estimand vocabulary (hard rule 2) ────────────────────────────────
    case("unknown triage estimand rejected", False, r"unknown estimand",
         [base_row(estimand="triage.made_up@v1")]),
    case("unknown speed estimand rejected (whitelist is not per-family)", False,
         r"unknown estimand", [speed_row(estimand="speed.made_up@v1")]),
    case("unversioned name rejected", False, r"unknown estimand",
         [base_row(estimand="triage.route_accuracy")]),

    # ── Triage threshold presence — per key (#1 DA-1; codex R1 A) ────────
    case("both thresholds missing rejected", False,
         r"condition missing.*triage_frag_max.*triage_text_min",
         [base_row(condition={"triage_text_min": DELETE, "triage_frag_max": DELETE})]),
    case("only text_min missing rejected", False, r"condition missing.*triage_text_min",
         [base_row(condition={"triage_text_min": DELETE})]),
    case("only frag_max missing rejected", False, r"condition missing.*triage_frag_max",
         [base_row(condition={"triage_frag_max": DELETE})]),

    # ── Triage threshold values — symmetric per key (#1 R3; codex R1 B) ──
    case("null text_min rejected", False, r"triage_text_min must be",
         [base_row(condition={"triage_text_min": None})]),
    case("null frag_max rejected", False, r"triage_frag_max must be",
         [base_row(condition={"triage_frag_max": None})]),
    case("list text_min rejected without traceback", False, r"triage_text_min must be",
         [base_row(condition={"triage_text_min": [200]})]),
    case("list frag_max rejected without traceback", False, r"triage_frag_max must be",
         [base_row(condition={"triage_frag_max": [0.6]})]),
    case("bool text_min rejected", False, r"triage_text_min must be",
         [base_row(condition={"triage_text_min": True})]),
    case("bool frag_max rejected", False, r"triage_frag_max must be",
         [base_row(condition={"triage_frag_max": True})]),
    case("negative text_min rejected", False, r"triage_text_min must be",
         [base_row(condition={"triage_text_min": -5})]),
    case("out-of-domain frag_max rejected", False, r"triage_frag_max must be",
         [base_row(condition={"triage_frag_max": 1.5})]),

    # ── Threshold finiteness (#1 R4) — both lexical paths, both keys ─────
    case("text_min literal 1e309 (parses to inf) rejected", False, r"finite",
         raw_lines=[raw_row(base_row(), triage_text_min="1e309")]),
    case("text_min Infinity token rejected", False, r"finite",
         [base_row(condition={"triage_text_min": 1e309})]),  # json.dumps emits Infinity
    case("text_min NaN rejected", False, r"triage_text_min must be",
         raw_lines=[raw_row(base_row(), triage_text_min="NaN")]),
    case("frag_max NaN rejected", False, r"triage_frag_max must be",
         raw_lines=[raw_row(base_row(), triage_frag_max="NaN")]),
    case("arbitrarily large int threshold accepted (no OverflowError)", True,
         r"pass hard checks", [base_row(condition={"triage_text_min": 10 ** 400})]),

    # ── Non-triage rows must omit threshold keys — per key (codex R1 C) ──
    case("non-triage row carrying text_min rejected", False, r"only valid on triage",
         [speed_row(condition={"triage_text_min": 200})]),
    case("non-triage row carrying frag_max rejected", False, r"only valid on triage",
         [speed_row(condition={"triage_frag_max": 0.6})]),
    case("non-triage row carrying both keys rejected", False, r"only valid on triage",
         [speed_row(condition={"triage_text_min": 200, "triage_frag_max": 0.6})]),

    # ── Value ranges — per direction (codex R1 D) ────────────────────────
    case("accuracy value above 1 rejected", False, r"must be in \[0, 1\]",
         [base_row(value=1.5)]),
    case("accuracy negative value rejected", False, r"must be in \[0, 1\]",
         [base_row(value=-0.1)]),
    case("accuracy NaN value rejected", False, r"value must be finite",
         raw_lines=[raw_row(base_row(), value="NaN")]),
    case("speed value zero rejected", False, r"positive milliseconds",
         [speed_row(value=0)]),
    case("speed negative value rejected", False, r"positive milliseconds",
         [speed_row(value=-3)]),
    case("speed NaN value rejected", False, r"value must be finite",
         raw_lines=[raw_row(speed_row(), value="NaN")]),
    case("speed Infinity value rejected", False, r"value must be finite",
         raw_lines=[raw_row(speed_row(), value="1e309")]),

    # ── Row structure (representatives of uniform mechanisms) ────────────
    case("tier other than T2-community rejected", False, r"tier must be",
         [base_row(tier="T1")]),
    case("missing required key rejected (machine_id as representative)", False,
         r"missing.*machine_id",
         [{k: v for k, v in base_row().items() if k != "machine_id"}]),
    case("condition not an object rejected", False, r"condition is not an object",
         [base_row(condition="not-a-dict")]),
    case("unknown corpus_id rejected", False, r"not in corpus/manifest",
         [base_row(corpus_id="nope")]),
    case("bad measured_at rejected", False, r"measured_at must be ISO-8601",
         [base_row(measured_at="yesterday")]),
    case("malformed filename rejected", False, r"filename does not match", [base_row()],
         filename="bad-name.jsonl"),
    case("duplicate rows rejected", False, r"bitwise-duplicate of", [base_row(), base_row()]),
    case("broken JSON line rejected with diagnosis", False, r"invalid JSON \(",
         raw_lines=["{not json"]),
]

# Known-gap pinning (strict-xfail): map a case name to the tracking issue while
# a KNOWN validator gap makes it fail its strict expectation. A pinned case that
# starts passing strictly FAILS the suite ("fix landed — remove the pin").
# Empty right now: the bench#4 pin (speed NaN admitted) was redeemed when #4
# landed — exactly the lifecycle this mechanism exists for.
KNOWN_GAPS = {}


def main():
    failures = []
    gaps_hit = []
    strict_passed_pins = set()
    passed = 0
    for c in CASES:
        code, output = run_validator(c["rows"], filename=c["filename"],
                                     raw_lines=c["raw_lines"])
        ok = (code == 0)
        problems = []
        # Traceback check runs for EVERY case, including known-gap pins —
        # a crash is never an acceptable way to be wrong (codex R2 finding).
        if "Traceback" in output:
            problems.append("validator raised a traceback — defects must be controlled errors")
        if ok != c["expect_ok"] and not problems and c["name"] in KNOWN_GAPS:
            gaps_hit.append((c["name"], KNOWN_GAPS[c["name"]]))
            print(f"gap   {c['name']} — {KNOWN_GAPS[c['name']]}")
            continue
        if ok != c["expect_ok"]:
            problems.append(f"exit={code}, expected {'ok' if c['expect_ok'] else 'FAIL'}")
        if c["pattern"] and not re.search(c["pattern"], output):
            problems.append(f"output lacks /{c['pattern']}/")
        if problems:
            failures.append((c["name"], problems, output.strip()[:300]))
            print(f"FAIL  {c['name']}: {'; '.join(problems)}")
        else:
            # True XPASS candidates only: a pinned case that passed EVERY
            # strict assertion (codex R3 — a pinned case failing on a
            # traceback or pattern is a plain failure, not a stale pin).
            if c["name"] in KNOWN_GAPS:
                strict_passed_pins.add(c["name"])
            passed += 1
            print(f"ok    {c['name']}")
    # A pin naming no case is a suite-config error, not a gap.
    case_names = {c["name"] for c in CASES}
    for name in sorted(set(KNOWN_GAPS) - case_names):
        failures.append((name, ["KNOWN_GAPS pin references no existing case — config error"], ""))
        print(f"FAIL  {name}: KNOWN_GAPS pin references no existing case")
    # Strict-xfail: a pin whose case now passes all strict assertions means
    # the tracked fix landed — fail loudly so the pin gets removed.
    for name in sorted(strict_passed_pins):
        failures.append((name, ["KNOWN_GAPS pin is stale — the tracked fix landed; "
                                "remove the pin and keep the strict assertion"], ""))
        print(f"FAIL  {name}: stale KNOWN_GAPS pin (fix landed — remove the pin)")
        passed -= 1
    print(f"\n{passed}/{len(CASES)} cases passed"
          + (f", {len(gaps_hit)} known gap(s) pinned" if gaps_hit else ""))
    if failures:
        for name, _, snippet in failures:
            print(f"\n--- {name} ---\n{snippet}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
