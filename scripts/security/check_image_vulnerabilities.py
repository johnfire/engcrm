"""Fail closed on incomplete image scans and every high/critical vulnerability."""
import json
import sys
from pathlib import Path


def blocked_findings(report: dict) -> list[str]:
    operating_system = report.get("Metadata", {}).get("OS", {})
    scans = report.get("Results", [])
    if (report.get("SchemaVersion") != 2 or operating_system.get("Family") not in {"alpine", "debian"}
            or not any(scan.get("Class") == "os-pkgs" for scan in scans)):
        raise ValueError("A complete supported OS image vulnerability scan is required")
    if operating_system.get("EOSL"):
        raise ValueError("End-of-life operating systems cannot be released")
    blocked = []
    for scan in scans:
        for finding in scan.get("Vulnerabilities") or []:
            severity = finding["Severity"]
            if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}:
                raise ValueError("Unrecognized vulnerability severity")
            if severity in {"HIGH", "CRITICAL", "UNKNOWN"}:
                blocked.append(f"{finding['VulnerabilityID']} {finding['PkgName']} {finding['InstalledVersion']} ({severity})")
    return blocked


def main() -> int:
    try:
        blocked = blocked_findings(json.loads(Path(sys.argv[1]).read_text()))
    except (ValueError, KeyError, TypeError, OSError, IndexError) as failure:
        print(f"Image scan rejected: {failure}", file=sys.stderr)
        return 1
    if blocked:
        print("Release blocked by image vulnerabilities:\n" + "\n".join(blocked), file=sys.stderr)
        return 1
    print("Image scan passed: no high, critical or unknown-severity findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
