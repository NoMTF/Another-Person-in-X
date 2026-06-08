#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
from typing import Any


DEFAULT_PERSONA_KEYWORDS = [
    "跨性别",
    "mtf",
    "trans",
    "小药娘",
    "hrt",
    "女装",
    "赛博",
    "ai",
    "机器人",
    "猫",
    "喵",
    "游戏",
    "二次元",
    "好好活着",
    "孤独",
    "亲密关系",
    "可爱",
    "抽象",
]

HIGH_RISK_RE = re.compile(
    r"(自杀|自残|自伤|轻生|结束这一切|最后一条|遗书|亖|死掉|死了|想死|去死|"
    r"安眠药|佐匹克隆|\d+\s*(?:mg|g|克|片)|过量|od|开盒|人肉|裸照|色情交易|未成年裸|"
    r"杀人|炸|枪|转发扩散|冲了|网暴|挂人|举报他全家)",
    re.I,
)


def strip_urls(text: str) -> str:
    return re.sub(r"https?://\S+", " ", str(text or ""))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def recursive_strings(value: Any, depth: int = 0) -> list[str]:
    if depth > 4 or value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, dict):
        out: list[str] = []
        for key, child in value.items():
            out.extend(recursive_strings(key, depth + 1))
            out.extend(recursive_strings(child, depth + 1))
        return out
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for child in list(value)[:40]:
            out.extend(recursive_strings(child, depth + 1))
        return out
    out: list[str] = []
    for attr in (
        "url",
        "expanded_url",
        "display_url",
        "text",
        "full_text",
        "name",
        "screen_name",
        "username",
        "quoted_status_permalink",
        "quoted_status_id",
        "quoted_status_id_str",
        "conversation_id",
        "conversation_id_str",
        "entities",
        "urls",
        "card",
        "legacy",
        "quote",
        "quoted",
        "quoted_tweet",
        "quoted_status",
        "quoted_status_result",
        "quoted_result",
        "retweeted_tweet",
        "retweeted_status",
        "retweeted_status_result",
    ):
        child = getattr(value, attr, None)
        if child is not None:
            out.extend(recursive_strings(child, depth + 1))
    return out


def reference_strings(tweet: dict[str, Any]) -> list[str]:
    values = [
        tweet.get("text"),
        tweet.get("urls"),
        tweet.get("entities"),
        tweet.get("quote"),
        tweet.get("quoted"),
        tweet.get("quoted_tweet"),
        tweet.get("quoted_status"),
        tweet.get("quoted_status_result"),
        tweet.get("quoted_result"),
        tweet.get("quoted_status_permalink"),
        tweet.get("quoted_status_id"),
        tweet.get("quoted_status_id_str"),
        tweet.get("conversation_id"),
        tweet.get("conversation_id_str"),
        tweet.get("card"),
        tweet.get("legacy"),
        tweet.get("retweeted_tweet"),
        tweet.get("retweeted_status"),
        tweet.get("retweeted_status_result"),
    ]
    out: list[str] = []
    for value in values:
        out.extend(recursive_strings(value))
    return out


QUOTE_KEYS = (
    "quote",
    "quoted",
    "quoted_tweet",
    "quoted_status",
    "quoted_status_result",
    "quoted_result",
)


REPOST_KEYS = (
    "retweeted_tweet",
    "retweeted_status",
    "retweeted_status_result",
    "retweet",
    "retweeted",
)


def _nested_user_screen_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    user = value.get("user") or value.get("author") or {}
    if not isinstance(user, dict):
        return ""
    return str(user.get("screen_name") or user.get("username") or "")


def _nested_id(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("id") or value.get("id_str") or value.get("rest_id") or "")


def _contains_own_object(tweet: dict[str, Any], keys: tuple[str, ...], username: str, monitored_ids: set[str]) -> bool:
    username = username.lower()
    for key in keys:
        value = tweet.get(key)
        if isinstance(value, dict):
            screen_name = _nested_user_screen_name(value).lower()
            nested_id = _nested_id(value)
            if screen_name == username or (nested_id and nested_id in monitored_ids):
                return True
            result = value.get("result")
            if isinstance(result, dict):
                screen_name = _nested_user_screen_name(result).lower()
                nested_id = _nested_id(result)
                if screen_name == username or (nested_id and nested_id in monitored_ids):
                    return True
    legacy = tweet.get("legacy") if isinstance(tweet.get("legacy"), dict) else {}
    for key in keys:
        value = legacy.get(key) if isinstance(legacy, dict) else None
        if isinstance(value, dict):
            screen_name = _nested_user_screen_name(value).lower()
            nested_id = _nested_id(value)
            if screen_name == username or (nested_id and nested_id in monitored_ids):
                return True
    return False


def mentions_or_quotes_own(tweet: dict[str, Any], username: str, monitored_tweet_ids: list[str] | None = None) -> dict[str, Any]:
    username = username.strip().lstrip("@")
    monitored_ids = {str(item) for item in monitored_tweet_ids or [] if str(item)}
    mention_re = re.compile(rf"(?<![A-Za-z0-9_])@?{re.escape(username)}(?![A-Za-z0-9_])", re.I)
    own_status_re = re.compile(rf"(?:x|twitter)\.com/{re.escape(username)}/status/(\d+)", re.I)
    any_status_re = re.compile(r"(?:x|twitter)\.com/[^/\s]+/status/(\d+)", re.I)
    blob = " ".join(reference_strings(tweet))
    mention = bool(mention_re.search(blob))
    quote_url = bool(own_status_re.search(blob))
    monitored_url = any(match.group(1) in monitored_ids for match in any_status_re.finditer(blob))
    quote_obj = _contains_own_object(tweet, QUOTE_KEYS, username, monitored_ids)
    repost_obj = _contains_own_object(tweet, REPOST_KEYS, username, monitored_ids)
    kinds = []
    if tweet.get("in_reply_to"):
        kinds.append("reply")
    if mention:
        kinds.append("mention")
    if quote_url or monitored_url or quote_obj:
        kinds.append("quote")
    if repost_obj:
        kinds.append("repost")
    return {
        "matched": bool(kinds),
        "kinds": kinds,
        "mention": mention,
        "quote": quote_url or monitored_url or quote_obj,
        "repost": repost_obj,
    }


def is_high_risk(text: str) -> bool:
    return bool(HIGH_RISK_RE.search(strip_urls(text)))


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    haystack = strip_urls(text).lower()
    hits: list[str] = []
    for keyword in keywords:
        keyword = keyword.strip().lower()
        if not keyword:
            continue
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(keyword)}(?![A-Za-z0-9_])", haystack, re.I):
            hits.append(keyword)
    return hits


def source_priority(source: str) -> int:
    if "get_latest_timeline" in source or "get_timeline" in source:
        return 100
    if "monitor_user" in source:
        return 85
    if "search" in source:
        return 55
    return 40


def rank_browse_candidates(candidates: list[dict[str, Any]], keywords: list[str] | None = None) -> list[dict[str, Any]]:
    keywords = keywords or DEFAULT_PERSONA_KEYWORDS
    ranked: list[dict[str, Any]] = []
    for item in candidates:
        text = clean_text(item.get("text", ""))
        if is_high_risk(text):
            continue
        source = str(item.get("source") or "")
        hits = keyword_hits(" ".join([text, source, str(item.get("user") or ""), str(item.get("quote") or "")]), keywords)
        enriched = dict(item)
        enriched["text"] = text
        source_rank = source_priority(source)
        persona_score = min(40, len(hits) * 8)
        enriched["persona_hits"] = hits[:8]
        enriched["source_rank"] = source_rank
        enriched["persona_score"] = persona_score
        enriched["priority_score"] = source_rank * 1000 + persona_score
        ranked.append(enriched)
    ranked.sort(
        key=lambda item: (
            -int(item.get("source_rank") or 0),
            -int(item.get("persona_score") or 0),
            random.random(),
        )
    )
    return ranked


def main() -> int:
    parser = argparse.ArgumentParser(description="Score X/Twitter interactions and browse candidates for persona agents.")
    parser.add_argument("--username", default="")
    parser.add_argument("--mode", choices=["interaction", "browse"], required=True)
    parser.add_argument("--input", required=True, help="JSON file containing a tweet object or candidate list.")
    args = parser.parse_args()
    with open(args.input, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if args.mode == "interaction":
        print(json.dumps(mentions_or_quotes_own(data, args.username), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(rank_browse_candidates(data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
