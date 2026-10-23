#!/usr/bin/env python3
"""Create a non-mutating integrity catalog for the legacy DEVELOPMENT corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent


def digest_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_and_raw_quality(path: Path) -> tuple[str, int]:
    digest = hashlib.sha512()
    nonfinite_samples = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
            values = np.frombuffer(chunk, dtype=np.complex64)
            nonfinite_samples += int(np.sum(~np.isfinite(values.real) | ~np.isfinite(values.imag)))
    return digest.hexdigest(), nonfinite_samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-raw", action="store_true", help="stream all raw bytes and verify embedded SHA-512")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "artifacts" / "datasets" / "legacy-development-snapshot-v3.json",
    )
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        raise SystemExit(f"refused: immutable catalog already exists: {output}")

    schema = json.loads((REPO_ROOT / "schemas" / "recording.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    records = []
    raw_bytes = 0
    source_seconds = 0.0
    schema_valid = 0
    verified = 0
    total_nonfinite_samples = 0
    for session_dir in sorted((REPO_ROOT / "data" / "raw").iterdir()):
        if not session_dir.is_dir():
            continue
        manifest_path = session_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        session_id = manifest["session_id"]
        data_path = session_dir / f"{session_id}.sigmf-data"
        metadata_path = session_dir / f"{session_id}.sigmf-meta"
        sigmf = json.loads(metadata_path.read_text(encoding="utf-8"))
        embedded_sha512 = sigmf["global"].get("core:sha512")
        byte_count = data_path.stat().st_size
        sample_rate = float(manifest["sample_rate_hz"])
        samples = byte_count // 8
        errors = sorted(error.message for error in validator.iter_errors(manifest))
        if not errors:
            schema_valid += 1
        observed_sha512 = None
        hash_verified = None
        nonfinite_samples = None
        if args.verify_raw:
            observed_sha512, nonfinite_samples = digest_and_raw_quality(data_path)
            hash_verified = observed_sha512 == embedded_sha512
            if not hash_verified:
                raise SystemExit(f"raw integrity failure: {data_path}")
            verified += 1
            total_nonfinite_samples += nonfinite_samples
        label_path = REPO_ROOT / "data" / "labels" / f"{session_id}.jsonl"
        records.append(
            {
                "session_directory": session_dir.name,
                "session_id": session_id,
                "synthetic": bool(manifest.get("synthetic", False)),
                "manifest_schema_v1_valid": not errors,
                "manifest_schema_error_count": len(errors),
                "manifest_sha256": digest_file(manifest_path, "sha256"),
                "sigmf_metadata_sha256": digest_file(metadata_path, "sha256"),
                "data_relative_path": str(data_path.relative_to(REPO_ROOT)),
                "data_bytes": byte_count,
                "complex64_samples": samples,
                "sample_rate_hz": sample_rate,
                "duration_s": samples / sample_rate,
                "embedded_sha512": embedded_sha512,
                "observed_sha512": observed_sha512,
                "raw_hash_verified": hash_verified,
                "label_file": str(label_path.relative_to(REPO_ROOT)) if label_path.exists() else None,
                "label_file_sha256": digest_file(label_path, "sha256") if label_path.exists() else None,
                "nonfinite_complex_samples": nonfinite_samples,
            }
        )
        raw_bytes += byte_count
        source_seconds += samples / sample_rate

    processed_paths = [
        REPO_ROOT / "data" / "processed" / "g3_features.parquet",
        REPO_ROOT / "data" / "processed" / "g3_features_v2_conflict_free.parquet",
    ]
    raw_hash_counts = Counter(item["observed_sha512"] or item["embedded_sha512"] for item in records)
    catalog = {
        "schema_version": "1.0",
        "snapshot_id": "legacy-development-snapshot-v3",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": {
            "path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
            "sha256": digest_file(Path(__file__).resolve(), "sha256"),
            "numpy_version": np.__version__,
        },
        "environment": "DEVELOPMENT",
        "raw_bytes_modified": False,
        "raw_hash_verification_requested": args.verify_raw,
        "summary": {
            "sessions": len(records),
            "real_sessions": sum(not item["synthetic"] for item in records),
            "synthetic_sessions": sum(item["synthetic"] for item in records),
            "raw_bytes": raw_bytes,
            "source_seconds": source_seconds,
            "current_schema_valid_manifests": schema_valid,
            "raw_hashes_verified": verified,
            "whole_file_duplicate_groups": sum(count > 1 for count in raw_hash_counts.values()),
            "nonfinite_complex_samples": total_nonfinite_samples if args.verify_raw else None,
            "sessions_with_labels": sum(item["label_file"] is not None for item in records),
        },
        "processed_artifacts": [
            {
                "path": str(path.relative_to(REPO_ROOT)),
                "bytes": path.stat().st_size,
                "sha256": digest_file(path, "sha256"),
            }
            for path in processed_paths
            if path.is_file()
        ],
        "limitations": [
            "legacy manifests do not validate schema v1 and must not be rewritten in place",
            "participant, site, room, consent, approval, quality, and code provenance are historically incomplete",
            "corpus appears to contain one self-testing researcher in one laboratory",
            "current corpus is train/development-only and is not an independent test cohort",
        ],
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **catalog["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
