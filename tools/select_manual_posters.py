#!/usr/bin/env python3
"""Choose which uploaded posters appear in the current carousel."""

from __future__ import annotations

import argparse

from manual_posters import available_images, select_images


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filenames", default="", help="Comma-separated image filenames; empty clears the manual selection.")
    parser.add_argument("--include-generated", choices=("true", "false"), default="true")
    args = parser.parse_args()
    print("Available images:")
    for filename in available_images():
        print(f"  {filename}")
    select_images(args.filenames, args.include_generated == "true")


if __name__ == "__main__":
    main()
