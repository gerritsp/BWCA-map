#!/usr/bin/env python3
"""Verify that Caddy permits every inline script in an HTML artifact."""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
from pathlib import Path


SCRIPT_PATTERN = re.compile(
    r"<script\b(?P<attributes>[^>]*)>(?P<body>.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
SRC_PATTERN = re.compile(r"(?:^|\s)src\s*=", re.IGNORECASE)


def inline_script_hashes(html: str) -> list[str]:
    """Return CSP SHA-256 source expressions for all inline scripts."""
    hashes = []
    for match in SCRIPT_PATTERN.finditer(html):
        if SRC_PATTERN.search(match.group("attributes")):
            continue
        digest = hashlib.sha256(match.group("body").encode("utf-8")).digest()
        encoded = base64.b64encode(digest).decode("ascii")
        hashes.append(f"'sha256-{encoded}'")
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that a Caddyfile contains every inline-script CSP hash.",
    )
    parser.add_argument("html", type=Path, help="generated HTML file to inspect")
    parser.add_argument(
        "caddyfile",
        nargs="?",
        type=Path,
        help="Caddyfile whose Content-Security-Policy should be checked",
    )
    parser.add_argument(
        "--print-hashes",
        action="store_true",
        help="print the required CSP hashes without checking a Caddyfile",
    )
    args = parser.parse_args()

    if not args.print_hashes and args.caddyfile is None:
        parser.error("caddyfile is required unless --print-hashes is used")

    try:
        html = args.html.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"Unable to read {args.html}: {error}", file=sys.stderr)
        return 2

    required = inline_script_hashes(html)
    if not required:
        print(f"No inline scripts found in {args.html}", file=sys.stderr)
        return 1

    if args.print_hashes:
        print("\n".join(required))
        return 0

    try:
        caddy = args.caddyfile.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"Unable to read {args.caddyfile}: {error}", file=sys.stderr)
        return 2

    missing = [source for source in required if source not in caddy]
    if missing:
        print(
            f"CSP check failed for {args.html}; add the following to script-src in "
            f"{args.caddyfile}:",
            file=sys.stderr,
        )
        for source in missing:
            print(f"  {source}", file=sys.stderr)
        return 1

    print(
        f"Verified {len(required)} inline-script CSP hash(es) for {args.html} "
        f"in {args.caddyfile}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
