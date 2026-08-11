"""Verifies that every file listed in FREEZE_MANIFEST_v3.json still matches
its recorded SHA256 hash. Run this before every RGV v3 blind engine run
(stage 8) to prove the frozen case definitions/labels/evidence have not
been altered since freeze -- per the holdout integrity rule: any mismatch
means the holdout must be treated as compromised for blind-validation
purposes and re-frozen (a fresh freeze, not a silent overwrite) before use.

Usage: python verify_rgv3_freeze.py
Exit code 0 = all hashes match. Exit code 1 = at least one mismatch/missing file.
"""
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent / "gold_corpus/scientific_validity/final_holdout_v1"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main():
    manifest = json.loads((BASE / "FREEZE_MANIFEST_v3.json").read_text())
    print(f"freeze_id: {manifest['freeze_id']}")
    print(f"frozen_on_utc: {manifest['frozen_on_utc']}")
    print(f"n_cases: {manifest['n_cases']}")
    print()

    ok = True
    for rel_path, expected_hash in manifest["file_hashes"].items():
        full_path = BASE / rel_path
        if not full_path.exists():
            print(f"MISSING: {rel_path}")
            ok = False
            continue
        actual_hash = sha256_of(full_path)
        if actual_hash != expected_hash:
            print(f"MISMATCH: {rel_path}")
            print(f"  expected: {expected_hash}")
            print(f"  actual:   {actual_hash}")
            ok = False
        else:
            print(f"OK: {rel_path}")

    print()
    if ok:
        print("All files match the freeze manifest. Holdout integrity intact.")
        sys.exit(0)
    else:
        print(
            "INTEGRITY FAILURE: one or more files differ from the freeze "
            "manifest. Do NOT run the blind validation against this holdout "
            "until this is resolved (re-freeze from the current state and "
            "record why, or restore the frozen files)."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
