"""Read-only live coverage check for configured public employer ATS boards.

This tool fetches public listings through the same adapters used by the discovery
engine. It does not write to the employer registry, application database, or run
history. Only aggregate counts and source identifiers are written to the report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from careerorbit.discovery.sources import (
    AshbyJobBoardSource,
    GreenhouseBoardSource,
    LeverSiteSource,
    SmartRecruitersSource,
)

DEFAULT_REGISTRY = ROOT / "data" / "employer_sources.json"
DEFAULT_REPORT = ROOT / "reports" / "LIVE_SOURCE_COVERAGE_REPORT.json"


def _configured_entries(registry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        entry for entry in registry
        if entry.get("enabled", True)
        and str(entry.get("board_id") or "").strip()
        and str(entry.get("employer_name") or "").strip()
    ]


def _check_one(entry: dict[str, Any], days_back: int) -> dict[str, Any]:
    provider = str(entry.get("ats_provider") or "").strip().lower()
    employer = str(entry.get("employer_name") or "").strip()
    board_id = str(entry.get("board_id") or "").strip()
    try:
        if provider == "greenhouse":
            source = GreenhouseBoardSource(employer, board_id)
        elif provider == "lever":
            source = LeverSiteSource(employer, board_id)
        elif provider in ("smartrecruiters", "smart_recruiters"):
            source = SmartRecruitersSource(employer, board_id)
        elif provider == "ashby":
            source = AshbyJobBoardSource(employer, board_id)
        else:
            raise ValueError("unsupported_provider")
        jobs = source.fetch_jobs(days_back=days_back)
        return {
            "id": str(entry.get("id") or ""),
            "employer": employer,
            "provider": str(entry.get("ats_provider") or ""),
            "board_id": board_id,
            "status": "ok",
            "normalized_jobs": len(jobs),
        }
    except Exception as exc:
        return {
            "id": str(entry.get("id") or ""),
            "employer": employer,
            "provider": str(entry.get("ats_provider") or ""),
            "board_id": board_id,
            "status": "failed",
            "error_type": type(exc).__name__,
            "normalized_jobs": 0,
        }


def run_coverage_check(
    registry_path: Path = DEFAULT_REGISTRY,
    days_back: int = 30,
    max_workers: int = 6,
) -> dict[str, Any]:
    registry_bytes = registry_path.read_bytes()
    registry = json.loads(registry_bytes.decode("utf-8"))
    if not isinstance(registry, list):
        raise ValueError("employer source registry must be a JSON list")
    entries = _configured_entries(registry)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, 12))) as pool:
        futures = [pool.submit(_check_one, entry, days_back) for entry in entries]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: (row["employer"].casefold(), row["id"]))
    succeeded = sum(row["status"] == "ok" for row in results)
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "check_type": "read_only_public_ats_adapter_fetch",
        "days_back": days_back,
        "registry_file": str(registry_path.relative_to(ROOT)).replace("\\", "/"),
        "registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
        "configured_source_ids": sorted(row["id"] for row in results),
        "configured_sources": len(entries),
        "checked_sources": len(results),
        "succeeded_sources": succeeded,
        "failed_sources": len(results) - succeeded,
        "normalized_jobs": sum(row["normalized_jobs"] for row in results),
        "all_configured_sources_succeeded": bool(entries) and succeeded == len(entries),
        "sources": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--days-back", type=int, default=30)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if args.days_back < 1 or args.workers < 1:
        parser.error("--days-back and --workers must be positive")
    report = run_coverage_check(args.registry.resolve(), args.days_back, args.workers)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        "Live source coverage: "
        f"{report['succeeded_sources']}/{report['configured_sources']} adapters succeeded; "
        f"{report['normalized_jobs']} normalized listings in {report['days_back']} days."
    )
    print(f"Report: {args.report}")
    return 0 if report["all_configured_sources_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
