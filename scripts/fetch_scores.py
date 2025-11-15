#!/usr/bin/env python3
"""
Standalone data fetcher that writes the latest league snapshot to JSON.

Intended for scheduled runs (e.g., GitHub Actions cron) so the front-end
can stay completely static.
"""

import argparse
import json
import logging
from pathlib import Path

from tracker import ScoreFetcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch ESPN fantasy scores and write JSON output.")
    parser.add_argument(
        "--output",
        default="public/data/snapshot.json",
        help="Path to write the snapshot JSON (default: public/data/snapshot.json).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Number of spaces for JSON indentation (default: 2).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fetcher = ScoreFetcher()
    snapshot = fetcher.build_snapshot()

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=args.indent)
        handle.write("\n")

    logger.info("Snapshot written to %s (week %s)", output_path, snapshot.get("week"))


if __name__ == "__main__":
    main()
