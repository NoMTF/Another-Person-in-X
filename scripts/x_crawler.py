#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List


def tweet_to_row(tweet: Any, handle: str, source: str) -> Dict[str, Any]:
    user = getattr(tweet, "user", None)
    return {
        "id": str(getattr(tweet, "id", "")),
        "text": getattr(tweet, "text", "") or getattr(tweet, "full_text", ""),
        "author": getattr(user, "screen_name", "") or handle.lstrip("@"),
        "created_at": str(getattr(tweet, "created_at", "")),
        "url": f"https://x.com/{handle.lstrip('@')}/status/{getattr(tweet, 'id', '')}",
        "kind": "tweet",
        "source": source,
        "reply_count": getattr(tweet, "reply_count", None),
        "favorite_count": getattr(tweet, "favorite_count", None),
        "retweet_count": getattr(tweet, "retweet_count", None),
    }


async def crawl(handle: str, limit: int, tweet_type: str) -> List[Dict[str, Any]]:
    try:
        from twikit import Client  # type: ignore
    except Exception as exc:
        raise SystemExit("twikit is not installed; install it at runtime with pip") from exc
    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0 = os.environ.get("X_CT0", "")
    if not auth_token or not ct0:
        raise SystemExit("missing X_AUTH_TOKEN/X_CT0")
    client = Client("en-US")
    client.set_cookies({"auth_token": auth_token, "ct0": ct0})
    user = await client.get_user_by_screen_name(handle.lstrip("@"))
    rows: List[Dict[str, Any]] = []
    result = await client.get_user_tweets(user.id, tweet_type, count=min(40, max(1, limit)))
    while result and len(rows) < limit:
        for tweet in result:
            rows.append(tweet_to_row(tweet, handle, f"x:{handle}"))
            if len(rows) >= limit:
                break
        if len(rows) >= limit or not getattr(result, "next", None):
            break
        result = await result.next()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl X/Twitter posts into persona_distill-compatible JSONL.")
    parser.add_argument("--handle", required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--tweet-type", default="Tweets", choices=["Tweets", "Replies", "Media", "Likes"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = asyncio.run(crawl(args.handle, args.limit, args.tweet_type))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(path), "count": len(rows), "handle": args.handle}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
