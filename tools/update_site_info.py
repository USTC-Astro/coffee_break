#!/usr/bin/env python3
"""Update small public site metadata used by the static homepage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
INFO_FILE = BASE_DIR / "data" / "site_info.json"
DEFAULTS = {
    "default_time": "每周一下午 4:00",
    "default_venue": "WFST 远程观测室（物质科研楼 C1011）或理化大楼 18 楼院士工作站轮流举行",
    "weekly_time": "本周一",
    "weekly_venue": "WFST 远程观测室（物质科研楼 C1011）",
    "venues": [
        "理化大楼 18 楼院士工作站",
        "WFST 远程观测室（物质科研楼 C1011）",
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Update homepage site metadata")
    parser.add_argument("--weekly-time", "--time", default="", help="This week's Coffee Break time text")
    parser.add_argument("--weekly-venue", "--venue", default="", help="This week's Coffee Break venue text")
    args = parser.parse_args()

    info = DEFAULTS.copy()
    if INFO_FILE.exists():
        try:
            current = json.loads(INFO_FILE.read_text(encoding="utf-8"))
            if isinstance(current, dict):
                info.update({
                    k: v for k, v in current.items()
                    if isinstance(v, str) or (k == "venues" and isinstance(v, list))
                })
        except json.JSONDecodeError:
            pass

    if args.weekly_time.strip():
        info["weekly_time"] = args.weekly_time.strip()
    if args.weekly_venue.strip():
        info["weekly_venue"] = args.weekly_venue.strip()

    INFO_FILE.parent.mkdir(parents=True, exist_ok=True)
    INFO_FILE.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
