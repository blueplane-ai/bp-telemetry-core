#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared helpers for integration test harnesses."""

import json
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path("/tmp/bp-telemetry-core/bug_fix")


def save_test_results(results_dict: dict, test_suite_name: str, file_prefix: str) -> None:
    """Persist integration test results to JSON and text summary files."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results = {
        "test_suite": test_suite_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "passed": len(results_dict.get("passed", [])),
            "failed": len(results_dict.get("failed", [])),
            "skipped": len(results_dict.get("skipped", [])),
        },
        "passed": [{"name": n, "message": m} for n, m in results_dict.get("passed", [])],
        "failed": [{"name": n, "message": m} for n, m in results_dict.get("failed", [])],
        "skipped": [{"name": n, "message": m} for n, m in results_dict.get("skipped", [])],
    }

    # Save JSON
    result_file = RESULTS_DIR / f"{file_prefix}_results.json"
    with open(result_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📄 Results saved to: {result_file}")

    # Save text summary
    summary_file = RESULTS_DIR / f"{file_prefix}_summary.txt"
    with open(summary_file, "w") as f:
        f.write(f"{test_suite_name.replace('_', ' ').title()} - Integration Test Results\n")
        f.write("=" * 50 + "\n")
        f.write(f"Timestamp: {results['timestamp']}\n\n")
        f.write(f"Passed:  {results['summary']['passed']}\n")
        f.write(f"Failed:  {results['summary']['failed']}\n")
        f.write(f"Skipped: {results['summary']['skipped']}\n\n")

        sections = [
            ("passed", "✅", "PASSED"),
            ("failed", "❌", "FAILED"),
            ("skipped", "⏭️", "SKIPPED"),
        ]
        for key, emoji, title in sections:
            if results[key]:
                f.write(f"{title}:\n")
                for t in results[key]:
                    f.write(f"  {emoji} {t['name']}: {t['message']}\n")
                f.write("\n")

    print(f"📄 Summary saved to: {summary_file}")
