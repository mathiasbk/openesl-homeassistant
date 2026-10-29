#!/usr/bin/env python3
"""The CHANGELOG.md section for the version in manifest.json.

  python3 tools/changelog.py           prints the version
  python3 tools/changelog.py --notes   prints its section (the release text)
  python3 tools/changelog.py --check   fails when the section or its "### Upgrading" is missing
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def version():
    with open(os.path.join(ROOT, "custom_components", "openesl", "manifest.json")) as f:
        return json.load(f)["version"]


def section(ver):
    with open(os.path.join(ROOT, "CHANGELOG.md")) as f:
        text = f.read()
    m = re.search(r"^## %s\n(.*?)(?=^## |\Z)" % re.escape(ver), text, re.S | re.M)
    return m.group(1).strip() if m else None


def main():
    ver = version()
    notes = section(ver)
    if "--check" in sys.argv or "--notes" in sys.argv:
        if notes is None:
            sys.exit(f"CHANGELOG.md has no section '## {ver}' (the version in manifest.json)")
        if "### Upgrading" not in notes:
            sys.exit(f"CHANGELOG.md section {ver} has no '### Upgrading'")
    if "--notes" in sys.argv:
        print(notes)
    elif "--check" in sys.argv:
        print(f"CHANGELOG.md has {ver} with upgrade instructions")
    else:
        print(ver)


if __name__ == "__main__":
    main()
