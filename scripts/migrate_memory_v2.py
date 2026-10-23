#!/usr/bin/env python3
"""One-time serialization migration from archctl.memory.v1 to v2.

The statement, rationale, origin, references and pins stay unchanged. Only the
schema label and the content revision change.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from archctl.core.contracts import version
from archctl.core.io import InputError, digest, write_text
from archctl.core.memory import parse_memory

LEGACY = "archctl.memory.v1"


def migrate_file(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") == version("memory"):
        return False
    if data.get("schema_version") != LEGACY:
        raise InputError(f"Expected {LEGACY}: {path}")
    if "revision" in data:
        raw = {key: value for key, value in data.items() if key != "revision"}
        if digest(raw) != data["revision"]:
            raise InputError(f"Legacy memory revision does not match content: {path}")
    data["schema_version"] = version("memory")
    data.pop("revision", None)
    record = parse_memory(data)
    write_text(path, json.dumps(record.to_dict(), indent=2, ensure_ascii=False) + "\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path("architecture/memory"))
    args = parser.parse_args(argv)
    migrated = skipped = 0
    for path in sorted(args.directory.glob("*.json")):
        if migrate_file(path):
            migrated += 1
        else:
            skipped += 1
    print(json.dumps({"migrated": migrated, "skipped": skipped, "directory": str(args.directory)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
