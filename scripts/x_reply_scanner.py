#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable

from x_signal import mentions_or_quotes_own


STATUS_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:x|twitter)\.com/([^/\s]+)/status/(\d+)", re.I)


def status_ids_from_text(value: str) -> list[str]:
    return [match.group(2) for match in STATUS_URL_RE.finditer(str(value or ""))]


def load_json_items(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    with open(path, "r", encoding="utf-8-sig") as fh:
        payload = json.load(fh)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("interactions", "candidates", "tweets", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def primitive(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def normalize(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return str(value)
    if primitive(value):
        return value
    if isinstance(value, dict):
        return {str(k): normalize(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalize(item, depth + 1) for item in list(value)[:80]]

    out: dict[str, Any] = {}
    for key in (
        "id",
        "id_str",
        "rest_id",
        "text",
        "full_text",
        "created_at",
        "user",
        "author",
        "in_reply_to",
        "in_reply_to_status_id",
        "in_reply_to_status_id_str",
        "in_reply_to_screen_name",
        "conversation_id",
        "conversation_id_str",
        "quote",
        "quoted",
        "quoted_tweet",
        "quoted_status",
        "quoted_status_result",
        "retweeted_tweet",
        "retweeted_status",
        "retweeted_status_result",
        "entities",
        "urls",
        "card",
        "legacy",
    ):
        child = getattr(value, key, None)
        if child is not None:
            out[key] = normalize(child, depth + 1)
    if not out and hasattr(value, "__dict__"):
        out = {str(k): normalize(v, depth + 1) for k, v in vars(value).items() if not str(k).startswith("_")}
    return out or str(value)


def tweet_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("tweet_id") or item.get("id_str") or item.get("rest_id") or "")


def screen_name(item: dict[str, Any]) -> str:
    user = item.get("user") or item.get("author") or {}
    if isinstance(user, str):
        return user.lstrip("@")
    if isinstance(user, dict):
        return str(user.get("screen_name") or user.get("username") or user.get("handle") or "").lstrip("@")
    return ""


def tweet_url(item: dict[str, Any]) -> str:
    if item.get("url"):
        return str(item["url"])
    tid = tweet_id(item)
    handle = screen_name(item)
    if tid and handle:
        return f"https://x.com/{handle}/status/{tid}"
    if tid:
        return f"https://x.com/i/status/{tid}"
    return ""


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if isinstance(payload, list):
        return {str(item) for item in payload}
    if isinstance(payload, dict):
        return {str(item) for item in payload.get("seen", [])}
    return set()


def save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"seen": sorted(seen), "updated_at": int(time.time())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def post_json(base: str, path: str, payload: dict[str, Any], token: str = "") -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


async def maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


async def try_call(method: Any, *args: Any, **kwargs: Any) -> Any:
    return await maybe_await(method(*args, **kwargs))


async def call_first(method: Any, variants: Iterable[tuple[tuple[Any, ...], dict[str, Any]]]) -> Any:
    errors: list[str] = []
    for args, kwargs in variants:
        try:
            return await try_call(method, *args, **kwargs)
        except TypeError as exc:
            errors.append(str(exc))
            continue
    raise RuntimeError("; ".join(errors[-3:]) or "no callable signature matched")


async def fetch_tweet(client: Any, tweet_id_value: str) -> dict[str, Any] | None:
    for name in ("get_tweet_by_id", "get_tweet", "get_tweet_detail", "get_tweet_details"):
        method = getattr(client, name, None)
        if not method:
            continue
        try:
            result = await call_first(method, [((tweet_id_value,), {}), ((int(tweet_id_value),), {})])
            return normalize(result)
        except Exception:
            continue
    return None


async def search_tweets(client: Any, query: str, limit: int) -> list[dict[str, Any]]:
    method = getattr(client, "search_tweet", None) or getattr(client, "search_tweets", None)
    if not method:
        return []
    variants = [
        ((query,), {"product": "Latest", "count": limit}),
        ((query, "Latest"), {"count": limit}),
        ((query, "Latest", limit), {}),
        ((query,), {"count": limit}),
        ((query,), {}),
    ]
    result = await call_first(method, variants)
    return [normalize(item) for item in list(result or [])[:limit]]


async def get_notifications(client: Any, limit: int) -> list[dict[str, Any]]:
    for name in ("get_notifications", "get_notification_timeline", "get_notifications_timeline"):
        method = getattr(client, name, None)
        if not method:
            continue
        try:
            result = await call_first(method, [((), {"count": limit}), (((limit,), {}))])
            return [normalize(item) for item in list(result or [])[:limit]]
        except Exception:
            continue
    return []


async def live_items(
    tweet_ids: list[str],
    username: str,
    monitored_ids: list[str],
    limit: int,
    source_timeout: float,
) -> list[dict[str, Any]]:
    try:
        from twikit import Client  # type: ignore
    except Exception as exc:
        raise SystemExit("twikit is not installed; use --input for offline checks or install twikit on the target host") from exc
    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0 = os.environ.get("X_CT0", "")
    if not auth_token or not ct0:
        raise SystemExit("missing X_AUTH_TOKEN/X_CT0")
    client = Client("en-US")
    client.set_cookies({"auth_token": auth_token, "ct0": ct0})
    items: list[dict[str, Any]] = []

    async def with_timeout(coro: Any) -> Any:
        return await asyncio.wait_for(coro, timeout=source_timeout)

    for item_id_value in tweet_ids:
        try:
            item = await with_timeout(fetch_tweet(client, item_id_value))
            if item:
                item.setdefault("source", "direct_tweet")
                items.append(item)
        except Exception:
            continue

    queries = [f"@{username}", f"to:{username}", f"x.com/{username}/status"] if username else []
    queries.extend(f"conversation_id:{item_id_value}" for item_id_value in monitored_ids)
    queries.extend(f"x.com/i/status/{item_id_value}" for item_id_value in monitored_ids)
    for query in queries:
        try:
            found = await with_timeout(search_tweets(client, query, limit))
            for item in found:
                item.setdefault("source", f"search:{query}")
            items.extend(found)
        except Exception:
            continue

    try:
        notifications = await with_timeout(get_notifications(client, limit))
        for item in notifications:
            item.setdefault("source", "notifications")
        items.extend(notifications)
    except Exception:
        pass
    return items


def build_pending(item: dict[str, Any], signal: dict[str, Any], username: str) -> dict[str, Any] | None:
    tid = tweet_id(item)
    kinds = signal.get("kinds") or []
    pure_repost = "repost" in kinds and not any(kind in kinds for kind in ("reply", "mention", "quote"))
    if not tid or pure_repost or signal.get("skip_tool_actions"):
        return None
    reason = "X interaction matched " + ",".join(kinds)
    return {
        "action": "reply",
        "target": tid,
        "text": "",
        "reason": reason,
        "risk": "medium" if signal.get("prompt_injection") else "low",
        "metadata": {
            "source": item.get("source", ""),
            "kinds": kinds,
            "url": tweet_url(item),
            "screen_name": screen_name(item),
            "reply_target_ids": signal.get("reply_target_ids", []),
            "reply_target_match": signal.get("reply_target_match", False),
            "reply_to_username": signal.get("reply_to_username", False),
            "scanner": "x_reply_scanner",
            "username": username,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan X/Twitter replies, mentions, quotes, and repost evidence into pending actions.")
    parser.add_argument("--username", required=True, help="Active account handle without @.")
    parser.add_argument("--input", default="", help="Offline JSON tweet/list payload to scan.")
    parser.add_argument("--tweet-id", action="append", default=[], help="Specific tweet id to fetch and scan.")
    parser.add_argument("--tweet-url", action="append", default=[], help="Specific x.com/twitter.com status URL to fetch and scan.")
    parser.add_argument("--monitored-tweet-id", action="append", default=[], help="Own/root tweet id whose replies should be considered direct interactions.")
    parser.add_argument("--monitored-url", action="append", default=[], help="Own/root status URL whose replies should be considered direct interactions.")
    parser.add_argument("--seen-file", default="seen_replies.json")
    parser.add_argument("--include-seen", action="store_true")
    parser.add_argument("--mark-seen", action="store_true")
    parser.add_argument("--enqueue-pending", action="store_true")
    parser.add_argument("--admin-api", default="http://127.0.0.1:18880")
    parser.add_argument("--admin-token", default="")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--source-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--dry-run", action="store_true", help="Do not call twikit; scan --input only.")
    args = parser.parse_args()

    direct_ids = [str(item) for item in args.tweet_id]
    for url in args.tweet_url:
        direct_ids.extend(status_ids_from_text(url))
    monitored_ids = [str(item) for item in args.monitored_tweet_id]
    for url in args.monitored_url:
        monitored_ids.extend(status_ids_from_text(url))
    monitored_ids = list(dict.fromkeys([item for item in monitored_ids if item]))
    direct_ids = list(dict.fromkeys([item for item in direct_ids if item]))

    items = load_json_items(args.input)
    if not args.dry_run and direct_ids:
        items.extend(asyncio.run(live_items(direct_ids, args.username, monitored_ids, args.limit, args.source_timeout_seconds)))
    elif not args.dry_run and not items:
        items.extend(asyncio.run(live_items([], args.username, monitored_ids, args.limit, args.source_timeout_seconds)))

    seen_path = Path(args.seen_file)
    seen = load_seen(seen_path)
    matched: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []
    deduped: set[str] = set()
    for item in items:
        tid = tweet_id(item)
        if not tid or tid in deduped:
            continue
        deduped.add(tid)
        if tid in seen and not args.include_seen:
            continue
        signal = mentions_or_quotes_own(item, args.username, monitored_ids)
        if not signal.get("matched"):
            continue
        entry = {
            "id": tid,
            "url": tweet_url(item),
            "screen_name": screen_name(item),
            "text": str(item.get("text") or item.get("full_text") or "")[:280],
            "signal": signal,
            "source": item.get("source", ""),
        }
        matched.append(entry)
        pending = build_pending(item, signal, args.username)
        if pending and args.enqueue_pending:
            pending["metadata"]["scanner_matched_at"] = int(time.time())
            pending_results.append(post_json(args.admin_api, "/api/pending", pending, args.admin_token))
        elif pending:
            pending_results.append({"dry_run": True, "pending": pending})
        if args.mark_seen:
            seen.add(tid)

    if args.mark_seen:
        save_seen(seen_path, seen)

    print(
        json.dumps(
            {
                "ok": True,
                "matched_count": len(matched),
                "matched": matched,
                "pending": pending_results,
                "monitored_tweet_ids": monitored_ids,
                "direct_tweet_ids": direct_ids,
                "seen_file": str(seen_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
