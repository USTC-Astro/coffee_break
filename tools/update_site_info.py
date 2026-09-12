#!/usr/bin/env python3
"""Update small public site metadata used by the static homepage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
INFO_FILE = BASE_DIR / "data" / "site_info.json"
DEFAULTS = {
    "time": "每周五下午 4:00",
    "venue": "理化大楼 18 楼院士工作站 / WFST 远程观测室（物质科研楼 C1011）轮流安排",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Update homepage site metadata")
    parser.add_argument("--time", default="", help="Coffee Break time text")
    parser.add_argument("--venue", default="", help="Coffee Break venue text")
    args = parser.parse_args()

    info = DEFAULTS.copy()
    if INFO_FILE.exists():
        try:
            current = json.loads(INFO_FILE.read_text(encoding="utf-8"))
            if isinstance(current, dict):
                info.update({k: v for k, v in current.items() if isinstance(v, str)})
        except json.JSONDecodeError:
            pass

    if args.time.strip():
        info["time"] = args.time.strip()
    if args.venue.strip():
        info["venue"] = args.venue.strip()

    INFO_FILE.parent.mkdir(parents=True, exist_ok=True)
    INFO_FILE.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
