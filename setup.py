#!/usr/bin/env python3
"""
general-crm setup wizard (basic CLI version)

For the best setup experience, use the AI-powered interview in Claude Code:
    /setup-gcrm

The AI interview asks open-ended questions, suggests search terms, and generates
both gcrm/vertical.py and gcrm/vertical_context.md (a rich narrative document
that makes outreach emails more specific and personal).

This script is a fallback for users without Claude Code. It generates
gcrm/vertical.py only — no context document.

Usage:
    uv run python setup.py
"""
import sys
import textwrap
from pathlib import Path

VERTICAL_PATH = Path(__file__).parent / "gcrm" / "vertical.py"


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"\n{prompt}{suffix}\n> ").strip()
        if val:
            return val
        if default:
            return default
        print("  (required — please enter a value)")


def ask_multiline(prompt: str, example: str = "") -> str:
    print(f"\n{prompt}")
    if example:
        print(f"  Example: {example}")
    print("  Enter text, then press Enter twice to finish:")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    return "\n".join(line for line in lines if line).strip()


def ask_list(prompt: str, example: str = "") -> list[str]:
    print(f"\n{prompt}")
    if example:
        print(f"  Example: {example}")
    print("  Enter one item per line. Press Enter on an empty line when done:")
    items = []
    while True:
        line = input("  - ").strip()
        if not line:
            if items:
                break
            print("  (need at least one item)")
        else:
            items.append(line)
    return items


def ask_int(prompt: str, default: int) -> int:
    while True:
        val = input(f"\n{prompt} [{default}]\n> ").strip()
        if not val:
            return default
        try:
            return int(val)
        except ValueError:
            print("  (enter a number)")


def build_scan_levels(n: int) -> dict:
    levels = {}
    print(f"\nDefine {n} scan levels. Level 1 is always run first and should be your highest-priority targets.")
    for i in range(1, n + 1):
        print(f"\n--- Level {i} ---")
        label = ask(f"Level {i} label (short description of what this level searches for):")
        terms = ask_list(
            f"Google Maps search terms for Level {i}:",
            example="Coffee Shop, Café, Espresso Bar" if i == 1 else "",
        )
        levels[i] = {"label": label, "maps_terms": terms}
    return levels


def render_vertical(
    identity: str,
    goal: str,
    website: str,
    targets: str,
    fit_criteria: str,
    outreach_style: str,
    language: str,
    scored_types: list[str],
    fit_signals: list[str],
    anti_signals: list[str],
    scan_levels: dict,
) -> str:
    def pystr(s: str) -> str:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        if "\n" in escaped:
            lines = escaped.split("\n")
            indented = "\n    ".join(lines)
            return f'(\n    "{indented}"\n)'
        return f'"{escaped}"'

    def pylist(items: list[str]) -> str:
        inner = "\n".join(f'    "{item}",' for item in items)
        return f"[\n{inner}\n]"

    def pydict_levels(levels: dict) -> str:
        parts = []
        for lvl, info in sorted(levels.items()):
            terms = "\n".join(f'            "{t}",' for t in info["maps_terms"])
            parts.append(
                f"    {lvl}: {{\n"
                f'        "label": "{info["label"]}",\n'
                f"        \"maps_terms\": [\n{terms}\n        ],\n"
                f"    }},"
            )
        return "{\n" + "\n".join(parts) + "\n}"

    scored_set = "{" + ", ".join(f'"{t}"' for t in scored_types) + "}"

    return textwrap.dedent(f"""\
# gcrm/vertical.py
# ─────────────────────────────────────────────────────────────────────────────
# SWAP THIS FILE TO CHANGE THE VERTICAL.
# Everything else in the system reads from here.
# Run `python setup.py` to regenerate this file interactively.
# ─────────────────────────────────────────────────────────────────────────────

# Who you are and what you're selling
IDENTITY = {pystr(identity)}
GOAL = {pystr(goal)}
WEBSITE = {pystr(website)}

# What kinds of businesses you're targeting
TARGETS = {pystr(targets)}

# What makes a contact a strong vs weak fit (used by scout agent for scoring)
FIT_CRITERIA = {pystr(fit_criteria)}

# Tone and style for outreach emails
OUTREACH_STYLE = {pystr(outreach_style)}

# Default language for outreach ("de", "en", "fr", etc.)
LANGUAGE_DEFAULT = {pystr(language)}

# Scout: contact types that get LLM scoring. All other types are auto-promoted to cold.
SCORED_TYPES: set[str] = {scored_set}

# Scout: positive signals to look for in website/notes content
FIT_SIGNALS = {pylist(fit_signals)}

# Scout: negative signals — contacts matching these are dropped
ANTI_SIGNALS = {pylist(anti_signals)}

# Scan levels — what to search for at each depth.
SCAN_LEVELS: dict[int, dict] = {pydict_levels(scan_levels)}
""")


def main():
    print("=" * 60)
    print("  general-crm setup wizard")
    print("=" * 60)
    print("\nThis will create gcrm/vertical.py — the single file that")
    print("defines your target vertical. You can re-run this anytime.")

    if VERTICAL_PATH.exists():
        overwrite = input("\ngcrm/vertical.py already exists. Overwrite? [y/N] ").strip().lower()
        if overwrite != "y":
            print("Aborted.")
            sys.exit(0)

    print("\n--- About you ---")
    identity = ask("Who are you? (name, role, location):",
                   "Acme Coffee GmbH, B2B espresso machine distributor based in Munich")
    goal = ask("What is your goal?",
               "Find independent cafes and restaurants across Germany to pitch our espresso machines")
    website = ask("Your website (included in email signatures):", "https://example.com")

    print("\n--- Your targets ---")
    targets = ask("What types of businesses are you targeting?",
                  "independent cafes, restaurants, hotels, coworking spaces, corporate offices")

    print("\n--- Fit criteria ---")
    fit_criteria = ask_multiline(
        "Describe what makes a contact a strong vs weak fit for your outreach:",
        "Strong fit: independent owner-operated cafes, specialty coffee focus. "
        "Weak fit: chain locations, supermarkets, businesses with no coffee operation.",
    )

    print("\n--- Outreach style ---")
    outreach_style = ask("How should outreach emails sound?",
                         "direct, professional, B2B — not overly casual, not stiff")

    print("\n--- Language ---")
    language = ask("Default outreach language (ISO 639-1 code):", "de")

    print("\n--- Scout scoring ---")
    print("\nWhich contact type(s) need LLM scoring?")
    print("  All other types are automatically promoted to 'cold' (ready for outreach).")
    print("  Typically the type that requires the most judgment — e.g. gallery, distributor.")
    scored_input = ask("Contact types to LLM-score (comma-separated):", "gallery")
    scored_types = [t.strip() for t in scored_input.split(",") if t.strip()]

    fit_signals = ask_list(
        "Positive fit signals (words/phrases that indicate a good fit):",
        example="specialty coffee, third wave, espresso bar, owner-operated",
    )
    anti_signals = ask_list(
        "Negative fit signals (words/phrases that indicate a poor fit):",
        example="chain, franchise, vending machine, supermarket",
    )

    print("\n--- Scan levels ---")
    n_levels = ask_int("How many scan levels do you want?", default=3)
    scan_levels = build_scan_levels(n_levels)

    content = render_vertical(
        identity=identity,
        goal=goal,
        website=website,
        targets=targets,
        fit_criteria=fit_criteria,
        outreach_style=outreach_style,
        language=language,
        scored_types=scored_types,
        fit_signals=fit_signals,
        anti_signals=anti_signals,
        scan_levels=scan_levels,
    )

    VERTICAL_PATH.write_text(content, encoding="utf-8")
    print(f"\nWritten: {VERTICAL_PATH}")
    print("\nNext steps:")
    print("  1. Review gcrm/vertical.py and tweak any details")
    print("  2. Run: uv run python -m gcrm.supervisor.run")
    print("  3. Open the UI: uv run uvicorn gcrm.api.main:app --reload")


if __name__ == "__main__":
    main()
