#!/usr/bin/env python3
"""Structural linter for aigon-viewer-specific architectural rules.

Enforces rules that ruff cannot catch. Runs with stdlib only -- no dependencies.

Usage:
    python _scripts/structural_lint.py              # all rules
    python _scripts/structural_lint.py --rule VERSION_SYNC  # single rule
    python _scripts/structural_lint.py --help
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# --- Configuration -----------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = [
    PROJECT_ROOT / "aigon_viewer",
]

SKIP_DIRS = {"__pycache__", ".git", ".venv", "vendored"}


# --- Violation ---------------------------------------------------------------

@dataclass
class Violation:
    file: str
    line: int
    col: int
    rule_id: str
    message: str
    remediation: str = ""


# --- Rule checkers -----------------------------------------------------------

def check_version_sync() -> list[Violation]:
    """VERSION_SYNC: Root pyproject.toml version must match aigon_viewer/version.py."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    version_py = PROJECT_ROOT / "aigon_viewer" / "version.py"

    if not pyproject.exists() or not version_py.exists():
        return []

    # Extract version from pyproject.toml
    pyproject_version = None
    for line in pyproject.read_text().splitlines():
        m = re.match(r'^version\s*=\s*"([^"]+)"', line)
        if m:
            pyproject_version = m.group(1)
            break

    # Extract version from aigon_viewer/version.py
    app_version = None
    for line in version_py.read_text().splitlines():
        m = re.match(r'^__version__\s*=\s*"([^"]+)"', line)
        if m:
            app_version = m.group(1)
            break

    if pyproject_version is None or app_version is None:
        return []

    if pyproject_version != app_version:
        return [Violation(
            file="pyproject.toml",
            line=1, col=1,
            rule_id="VERSION_SYNC",
            message=f'pyproject.toml version "{pyproject_version}" != aigon_viewer/version.py "{app_version}"',
            remediation="Update both files to the same version",
        )]

    return []


# --- File collection ---------------------------------------------------------

def collect_files() -> list[Path]:
    """Collect all .py files from scan dirs, skipping excluded dirs."""
    files = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            if any(part in SKIP_DIRS for part in py_file.parts):
                continue
            files.append(py_file)
    return sorted(files)


def rel_path(filepath: Path) -> str:
    """Get path relative to project root."""
    try:
        return str(filepath.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(filepath)


# --- Rules registry ----------------------------------------------------------

LINE_RULES: dict[str, object] = {}

AST_RULES: dict[str, object] = {}

GLOBAL_RULES = {
    "VERSION_SYNC": check_version_sync,
}

ALL_RULES = list(LINE_RULES.keys()) + list(AST_RULES.keys()) + list(GLOBAL_RULES.keys())


# --- Reporter ----------------------------------------------------------------

def report(violations: list[Violation], active_rules: list[str]) -> int:
    """Print ruff-style output and summary table. Returns exit code."""
    if not violations:
        print(f"OK  No violations found ({len(active_rules)} rules checked)")
        return 0

    violations.sort(key=lambda v: (v.file, v.line))

    for v in violations:
        print(f"{v.file}:{v.line}:{v.col}: {v.rule_id} {v.message}")

    print()
    rule_counts: dict[str, int] = {}
    for v in violations:
        rule_counts[v.rule_id] = rule_counts.get(v.rule_id, 0) + 1

    print("Summary:")
    print(f"  {'Rule':<20} {'Violations':>10}")
    print(f"  {'-' * 20} {'-' * 10}")
    for rule_id in sorted(rule_counts.keys()):
        print(f"  {rule_id:<20} {rule_counts[rule_id]:>10}")
    print(f"  {'-' * 20} {'-' * 10}")
    print(f"  {'TOTAL':<20} {len(violations):>10}")

    return 1


# --- Main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Structural linter for aigon-viewer architectural rules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available rules: {', '.join(ALL_RULES)}",
    )
    parser.add_argument(
        "--rule", type=str, default=None,
        help="Run only this rule (e.g. --rule VERSION_SYNC)",
    )
    args = parser.parse_args()

    # Determine which rules to run
    if args.rule:
        rule_name = args.rule.upper()
        if rule_name not in ALL_RULES:
            print(f"Error: Unknown rule '{args.rule}'. Available: {', '.join(ALL_RULES)}")
            sys.exit(2)
        active_line_rules = {k: v for k, v in LINE_RULES.items() if k == rule_name}
        active_ast_rules = {k: v for k, v in AST_RULES.items() if k == rule_name}
        active_global_rules = {k: v for k, v in GLOBAL_RULES.items() if k == rule_name}
        active_rules = [rule_name]
    else:
        active_line_rules = LINE_RULES
        active_ast_rules = AST_RULES
        active_global_rules = GLOBAL_RULES
        active_rules = ALL_RULES

    # Collect and scan
    files = collect_files()
    all_violations: list[Violation] = []

    for filepath in files:
        rel = rel_path(filepath)

        # Line-based rules
        if active_line_rules:
            try:
                lines = filepath.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, PermissionError):
                continue

            for rule_id, checker in active_line_rules.items():
                all_violations.extend(checker(filepath, lines, rel))

        # AST-based rules
        for rule_id, checker in active_ast_rules.items():
            all_violations.extend(checker(filepath, rel))

    # Global rules (not per-file)
    for rule_id, checker in active_global_rules.items():
        all_violations.extend(checker())

    sys.exit(report(all_violations, active_rules))


if __name__ == "__main__":
    main()
