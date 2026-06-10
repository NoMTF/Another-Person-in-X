#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ActionResult:
    ok: bool
    action: str
    adapter: str
    dry_run: bool
    id: str = ""
    error: str = ""
    metadata: Dict[str, Any] = None


class BaseAdapter:
    name = "base"

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def post(self, text: str) -> ActionResult:
        return self._unsupported("post")

    def reply(self, tweet_id: str, text: str) -> ActionResult:
        return self._unsupported("reply")

    def like(self, tweet_id: str) -> ActionResult:
        return self._unsupported("like")

    def repost(self, tweet_id: str) -> ActionResult:
        return self._unsupported("repost")

    def quote(self, tweet_id: str, text: str, screen_name: str = "", url: str = "") -> ActionResult:
        return self._unsupported("quote")

    def follow(self, user_id_or_handle: str) -> ActionResult:
        return self._unsupported("follow")

    def report(self, user_id_or_handle: str, reason: str = "spam", tweet_id: str = "", confirm: str = "") -> ActionResult:
        return self._unsupported("report")

    def _unsupported(self, action: str) -> ActionResult:
        return ActionResult(False, action, self.name, self.dry_run, error="unsupported action", metadata={})


class TwikitAdapter(BaseAdapter):
    name = "twikit"

    def __init__(self, dry_run: bool = False, auth_token: str = "", ct0: str = "") -> None:
        super().__init__(dry_run)
        self.auth_token = auth_token or os.environ.get("X_AUTH_TOKEN", "")
        self.ct0 = ct0 or os.environ.get("X_CT0", "")

    def _client(self) -> Any:
        try:
            from twikit import Client  # type: ignore
        except Exception as exc:
            raise RuntimeError("twikit is not installed; install it at runtime with pip") from exc
        if not self.auth_token or not self.ct0:
            raise RuntimeError("missing X_AUTH_TOKEN/X_CT0")
        client = Client("en-US")
        client.set_cookies({"auth_token": self.auth_token, "ct0": self.ct0})
        return client

    def _dry_result(self, action: str, payload: Dict[str, Any]) -> Optional[ActionResult]:
        if self.dry_run:
            return ActionResult(True, action, self.name, True, id=f"dry-{int(time.time())}", metadata=payload)
        return None

    def _run(self, action: str, payload: Dict[str, Any], coro_factory: Any) -> ActionResult:
        dry = self._dry_result(action, payload)
        if dry:
            return dry
        try:
            result = asyncio.run(coro_factory(self._client()))
            rid = str(getattr(result, "id", "") or getattr(result, "rest_id", "") or "")
            return ActionResult(True, action, self.name, False, id=rid, metadata=payload)
        except Exception as exc:
            return ActionResult(False, action, self.name, False, error=str(exc), metadata=payload)

    @staticmethod
    def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
        try:
            if isinstance(obj, dict):
                return obj.get(name, default)
            return getattr(obj, name)
        except Exception:
            return default

    @classmethod
    def _current_user_retweeted(cls, tweet: Any) -> bool:
        for source in (tweet, cls._safe_getattr(tweet, "_legacy"), cls._safe_getattr(tweet, "legacy")):
            for name in ("retweeted", "retweeted_by_viewer", "is_retweeted"):
                value = cls._safe_getattr(source, name)
                if isinstance(value, bool):
                    return value
                if str(value).lower() in ("1", "true", "yes"):
                    return True
        return False

    @classmethod
    def _tweet_status_metadata(cls, tweet: Any) -> Dict[str, Any]:
        legacy = cls._safe_getattr(tweet, "_legacy") or cls._safe_getattr(tweet, "legacy") or {}
        user = cls._safe_getattr(tweet, "user") or cls._safe_getattr(tweet, "author")
        return {
            "tweet_id": str(cls._safe_getattr(tweet, "id") or cls._safe_getattr(tweet, "rest_id") or ""),
            "author": cls._safe_getattr(user, "screen_name"),
            "retweeted": cls._current_user_retweeted(tweet),
            "retweet_count": cls._safe_getattr(legacy, "retweet_count"),
        }

    async def _get_tweet_for_status(self, client: Any, tweet_id: str) -> Any:
        first_error: Exception | None = None
        try:
            tweets = await client.get_tweets_by_ids([str(tweet_id)])
            if tweets:
                return tweets[0]
        except Exception as exc:
            first_error = exc
        try:
            return await client.get_tweet_by_id(str(tweet_id))
        except Exception:
            if first_error:
                raise first_error
            raise

    async def _repost_verified(self, client: Any, tweet_id: str) -> ActionResult:
        payload: Dict[str, Any] = {"tweet_id": tweet_id}
        try:
            before_tweet = await self._get_tweet_for_status(client, tweet_id)
            before = self._tweet_status_metadata(before_tweet)
            payload["before"] = before
            if before.get("retweeted") is True:
                payload["after"] = before
                payload["already_reposted"] = True
                payload["verified"] = True
                return ActionResult(True, "repost", self.name, False, id=tweet_id, metadata=payload)
        except Exception as exc:
            payload["before_error"] = str(exc)

        response = await client.retweet(tweet_id)
        payload["response_status_code"] = self._safe_getattr(response, "status_code")
        payload["response_ok"] = self._safe_getattr(response, "is_success")
        try:
            response_json = response.json()
            payload["response_json"] = response_json
            created = (
                response_json.get("data", {})
                .get("create_retweet", {})
                .get("retweet_results", {})
                .get("result", {})
            )
            payload["created_retweet_id"] = str(created.get("rest_id") or "")
        except Exception:
            response_text = str(self._safe_getattr(response, "text", "") or "")
            if response_text:
                payload["response_text"] = response_text[:500]

        for _ in range(3):
            await asyncio.sleep(2)
            try:
                after_tweet = await self._get_tweet_for_status(client, tweet_id)
                after = self._tweet_status_metadata(after_tweet)
                payload["after"] = after
                if after.get("retweeted") is True:
                    payload["verified"] = True
                    return ActionResult(
                        True,
                        "repost",
                        self.name,
                        False,
                        id=str(payload.get("created_retweet_id") or tweet_id),
                        metadata=payload,
                    )
            except Exception as exc:
                payload["after_error"] = str(exc)

        payload["verified"] = False
        return ActionResult(False, "repost", self.name, False, error="repost was not verified on X", metadata=payload)

    def post(self, text: str) -> ActionResult:
        return self._run("post", {"text": text}, lambda client: client.create_tweet(text=text))

    def reply(self, tweet_id: str, text: str) -> ActionResult:
        return self._run("reply", {"tweet_id": tweet_id, "text": text}, lambda client: client.create_tweet(text=text, reply_to=tweet_id))

    def like(self, tweet_id: str) -> ActionResult:
        return self._run("like", {"tweet_id": tweet_id}, lambda client: client.favorite_tweet(tweet_id))

    def repost(self, tweet_id: str) -> ActionResult:
        dry = self._dry_result("repost", {"tweet_id": tweet_id})
        if dry:
            return dry
        try:
            return asyncio.run(self._repost_verified(self._client(), tweet_id))
        except Exception as exc:
            return ActionResult(False, "repost", self.name, False, error=str(exc), metadata={"tweet_id": tweet_id})

    def quote(self, tweet_id: str, text: str, screen_name: str = "", url: str = "") -> ActionResult:
        attachment_url = url or (f"https://x.com/{screen_name.lstrip('@')}/status/{tweet_id}" if screen_name else f"https://x.com/i/status/{tweet_id}")
        return self._run(
            "quote",
            {"tweet_id": tweet_id, "text": text, "attachment_url": attachment_url},
            lambda client: client.create_tweet(text=text, attachment_url=attachment_url),
        )

    def follow(self, user_id_or_handle: str) -> ActionResult:
        async def _follow(client: Any) -> Any:
            user_id = user_id_or_handle
            if not user_id_or_handle.isdigit():
                user = await client.get_user_by_screen_name(user_id_or_handle.lstrip("@"))
                user_id = user.id
            return await client.follow_user(user_id)

        return self._run("follow", {"user": user_id_or_handle}, _follow)

    def report(self, user_id_or_handle: str, reason: str = "spam", tweet_id: str = "", confirm: str = "") -> ActionResult:
        payload = {
            "user": user_id_or_handle,
            "reason": reason,
            "tweet_id": tweet_id,
            "confirm": bool(confirm),
        }
        dry = self._dry_result("report", payload)
        if dry:
            return dry
        return ActionResult(
            False,
            "report",
            self.name,
            False,
            error="twikit has no stable public report method; use the local X service /report endpoint with explicit live enablement",
            metadata=payload,
        )


class OfficialApiAdapter(BaseAdapter):
    name = "official-api"

    def _result(self, action: str, payload: Dict[str, Any]) -> ActionResult:
        if self.dry_run:
            return ActionResult(True, action, self.name, True, id=f"dry-{int(time.time())}", metadata=payload)
        return ActionResult(False, action, self.name, False, error="official X API adapter is reserved for paid API deployments", metadata=payload)

    def post(self, text: str) -> ActionResult:
        return self._result("post", {"text": text})

    def reply(self, tweet_id: str, text: str) -> ActionResult:
        return self._result("reply", {"tweet_id": tweet_id, "text": text})

    def like(self, tweet_id: str) -> ActionResult:
        return self._result("like", {"tweet_id": tweet_id})

    def repost(self, tweet_id: str) -> ActionResult:
        return self._result("repost", {"tweet_id": tweet_id})

    def quote(self, tweet_id: str, text: str, screen_name: str = "", url: str = "") -> ActionResult:
        return self._result("quote", {"tweet_id": tweet_id, "text": text, "screen_name": screen_name, "url": url})

    def follow(self, user_id_or_handle: str) -> ActionResult:
        return self._result("follow", {"user": user_id_or_handle})

    def report(self, user_id_or_handle: str, reason: str = "spam", tweet_id: str = "", confirm: str = "") -> ActionResult:
        return self._result("report", {"user": user_id_or_handle, "reason": reason, "tweet_id": tweet_id, "confirm": bool(confirm)})


def adapter_for(name: str, dry_run: bool) -> BaseAdapter:
    if name == "twikit":
        return TwikitAdapter(dry_run=dry_run)
    if name == "official-api":
        return OfficialApiAdapter(dry_run=dry_run)
    raise SystemExit(f"unknown adapter: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="X/Twitter adapter boundary for OpenClaw Agent Factory.")
    parser.add_argument("action", choices=["post", "reply", "like", "repost", "quote", "follow", "report"])
    parser.add_argument("--adapter", default="twikit", choices=["twikit", "official-api"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--text", default="")
    parser.add_argument("--tweet-id", default="")
    parser.add_argument("--screen-name", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--user", default="")
    parser.add_argument("--reason", default="spam")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    adapter = adapter_for(args.adapter, args.dry_run)
    if args.action == "post":
        result = adapter.post(args.text)
    elif args.action == "reply":
        result = adapter.reply(args.tweet_id, args.text)
    elif args.action == "like":
        result = adapter.like(args.tweet_id)
    elif args.action == "repost":
        result = adapter.repost(args.tweet_id)
    elif args.action == "quote":
        result = adapter.quote(args.tweet_id, args.text, screen_name=args.screen_name, url=args.url)
    elif args.action == "follow":
        result = adapter.follow(args.user)
    else:
        result = adapter.report(args.user or args.screen_name, reason=args.reason, tweet_id=args.tweet_id, confirm=args.confirm)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok or result.dry_run else 2


if __name__ == "__main__":
    raise SystemExit(main())
