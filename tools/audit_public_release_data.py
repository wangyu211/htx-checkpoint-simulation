"""Audit Git-tracked artifacts against the public-release data boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.governance.public_release import audit_paths


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    tracked = tracked_files()
    findings = audit_paths(PROJECT_ROOT, tracked)
    report = {
        "status": "PASS" if not findings else "FAIL",
        "tracked_file_count": len(tracked),
        "finding_count": len(findings),
        "findings": [
            {
                "code": finding.code,
                "path": finding.path,
                "detail": finding.detail,
            }
            for finding in findings
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
