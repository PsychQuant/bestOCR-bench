#!/usr/bin/env python3
"""Self-test for tools/validate_measurements.py — the submission CI gate.

Zero dependencies (stdlib only). Each case builds a throwaway fixture repo
(corpus manifest + measurement rows) in a tempdir, runs the validator as a
subprocess, and asserts on exit code + output pattern. Fixtures are
programmatic, not checked-in files, so cases stay self-describing.

The case set fossilizes the #1 R1–R4 verify assertions: every hard-check
branch that a real defect once slipped through (or nearly did) has a row here.
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


def base_row(**overrides):
    """A row that passes every hard check; overrides shape each case."""
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
    condition_overrides = overrides.pop("condition", None)
    row.update(overrides)
    if condition_overrides is not None:
        row["condition"] = {**row["condition"], **condition_overrides}
        # A sentinel of None means "delete this key".
        row["condition"] = {k: v for k, v in row["condition"].items() if v is not DELETE}
    return row


DELETE = object()


def speed_row(**overrides):
    row = base_row(estimand="speed.ms_per_page@v1", value=850.5)
    row["condition"] = {k: v for k, v in row["condition"].items()
                       if not k.startswith("triage_")}
    row.update(overrides)
    return row


def run_validator(rows, filename=FNAME, raw_lines=None):
    """Build fixture repo, run validator, return (exit_code, combined_output)."""
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


# (name, rows_or_raw, expect_ok, required_output_pattern)
CASES = [
    # Happy paths
    ("valid triage row passes", [base_row()], True, r"pass hard checks"),
    ("valid speed row passes (no thresholds required)", [speed_row()], True, r"pass hard checks"),

    # Estimand vocabulary (hard rule 2)
    ("unknown estimand rejected", [base_row(estimand="triage.made_up@v1")], False,
     r"unknown estimand"),
    ("unversioned name rejected", [base_row(estimand="triage.route_accuracy")], False,
     r"unknown estimand"),

    # Triage threshold presence (#1 R2 / DA-1)
    ("triage row missing thresholds rejected",
     [base_row(condition={"triage_text_min": DELETE, "triage_frag_max": DELETE})], False,
     r"condition missing.*triage"),

    # Triage threshold values (#1 R3)
    ("null thresholds rejected", [base_row(condition={"triage_text_min": None})], False,
     r"triage_text_min must be"),
    ("list threshold rejected without traceback",
     [base_row(condition={"triage_text_min": [200]})], False, r"triage_text_min must be"),
    ("bool threshold rejected", [base_row(condition={"triage_text_min": True})], False,
     r"triage_text_min must be"),
    ("out-of-domain frag_max rejected", [base_row(condition={"triage_frag_max": 1.5})], False,
     r"triage_frag_max must be"),

    # Finiteness (#1 R4): 1e309 parses to float inf
    ("infinite text_min rejected", [base_row(condition={"triage_text_min": 1e309})], False,
     r"finite"),
    ("arbitrarily large int threshold accepted (no OverflowError)",
     [base_row(condition={"triage_text_min": 10 ** 400})], True, r"pass hard checks"),

    # Non-triage rows must omit threshold keys (#1 R3, schema §3)
    ("non-triage row carrying threshold key rejected",
     [speed_row(condition={**speed_row()["condition"], "triage_text_min": 200})], False,
     r"only valid on triage"),

    # Value ranges per family
    ("accuracy value above 1 rejected", [base_row(value=1.5)], False,
     r"must be in \[0, 1\]"),
    ("speed value zero rejected", [speed_row(value=0)], False, r"positive milliseconds"),

    # Row structure
    ("tier other than T2-community rejected", [base_row(tier="T1")], False,
     r"tier must be"),
    ("missing required key rejected",
     [{k: v for k, v in base_row().items() if k != "machine_id"}], False, r"missing"),
    ("unknown corpus_id rejected", [base_row(corpus_id="nope")], False,
     r"not in corpus/manifest"),
    ("bad measured_at rejected", [base_row(measured_at="yesterday")], False,
     r"measured_at"),
    ("malformed filename rejected", [base_row()], False, r"filename",
     "bad-name.jsonl"),
    ("duplicate rows rejected", [base_row(), base_row()], False, r"duplicate"),
    ("broken JSON line rejected", None, False, r"", None, ["{not json"]),
]


def main():
    failures = []
    for case in CASES:
        name, rows, expect_ok, pattern = case[0], case[1], case[2], case[3]
        filename = case[4] if len(case) > 4 and case[4] else FNAME
        raw_lines = case[5] if len(case) > 5 else None
        code, output = run_validator(rows, filename=filename, raw_lines=raw_lines)
        ok = (code == 0)
        problems = []
        if ok != expect_ok:
            problems.append(f"exit={code}, expected {'ok' if expect_ok else 'FAIL'}")
        if pattern and not re.search(pattern, output):
            problems.append(f"output lacks /{pattern}/")
        if "Traceback" in output:
            problems.append("validator raised a traceback — defects must be controlled errors")
        if problems:
            failures.append((name, problems, output.strip()[:300]))
            print(f"FAIL  {name}: {'; '.join(problems)}")
        else:
            print(f"ok    {name}")
    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} cases passed")
    if failures:
        for name, _, snippet in failures:
            print(f"\n--- {name} ---\n{snippet}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
