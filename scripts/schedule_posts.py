#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict


def api_json(base: str, path: str, payload: Dict[str, Any], token: str = "") -> Dict[str, Any]:
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def random_times(day: datetime, count: int, start_hour: int, end_hour: int, seed: int | None) -> list[int]:
    rng = random.Random(seed)
    start = day.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = day.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if end <= start:
        end += timedelta(days=1)
    span = int((end - start).total_seconds())
    return sorted(int((start + timedelta(seconds=rng.randint(0, span))).timestamp()) for _ in range(count))


def main() -> int:
    parser = argparse.ArgumentParser(description="Create randomized pending original-post slots in the admin queue.")
    parser.add_argument("--admin-api", default="http://127.0.0.1:18880")
    parser.add_argument("--admin-token", default="")
    parser.add_argument("--count", type=int, default=16)
    parser.add_argument("--persona-slug", default="")
    parser.add_argument("--topic", default="original daily post")
    parser.add_argument("--start-hour", type=int, default=7)
    parser.add_argument("--end-hour", type=int, default=26)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    day = datetime.now(timezone.utc)
    slots = random_times(day, args.count, args.start_hour, args.end_hour, args.seed)
    results = []
    for slot in slots:
        payload = {
            "action": "post",
            "target": "",
            "text": "",
            "reason": f"scheduled slot {datetime.fromtimestamp(slot, timezone.utc).isoformat()} topic={args.topic}",
            "risk": "unknown",
            "persona_slug": args.persona_slug,
            "metadata": {"scheduled_at": slot, "topic": args.topic},
        }
        results.append(api_json(args.admin_api, "/api/pending", payload, args.admin_token))
    print(json.dumps({"scheduled": len(results), "slots": slots}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
