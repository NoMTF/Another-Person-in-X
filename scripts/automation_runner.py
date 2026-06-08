#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


MOODS = ["everyday", "excited", "tired", "serious", "sharp", "very-short", "long-form"]


@dataclass
class Candidate:
    action: str
    reason: str
    target: str = ""
    text: str = ""
    risk: str = "low"
    screen_name: str = ""
    url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def api_json(base: str, path: str, payload: Dict[str, Any] = None, token: str = "") -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


ACTION_FEATURES = {
    "post": "auto_post",
    "reply": "auto_reply",
    "like": "like",
    "repost": "repost",
    "quote": "quote",
    "follow": "follow",
}


def load_browse_items(path: str) -> List[Dict[str, Any]]:
    if not path:
        return []
    with open(path, "r", encoding="utf-8-sig") as fh:
        payload = json.load(fh)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("candidates", "tweets", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def user_screen_name(value: Any) -> str:
    if isinstance(value, str):
        return value.lstrip("@")
    if isinstance(value, dict):
        return str(value.get("screen_name") or value.get("username") or value.get("handle") or "").lstrip("@")
    return ""


def item_id(item: Dict[str, Any]) -> str:
    return str(item.get("id") or item.get("tweet_id") or item.get("id_str") or item.get("rest_id") or "")


def quote_text(item: Dict[str, Any], mood: str) -> str:
    hits = [str(hit) for hit in item.get("persona_hits") or [] if str(hit).strip()]
    if hits:
        focus = hits[0]
        if mood in {"serious", "long-form"}:
            return f"关于{focus}这点其实值得认真想一下"
        if mood in {"sharp", "very-short"}:
            return f"这个{focus}点到我了"
        return f"这个和{focus}有关的细节我会多看一眼"
    if mood == "very-short":
        return "这条我会停下来看看"
    if mood == "sharp":
        return "这条有点意思，先收进时间线"
    if mood == "long-form":
        return "这种细节比空泛情绪更值得被看见一点"
    return "这条挺值得看一下"


def rank_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return [
            {
                "id": "dry-run-target",
                "text": "dry-run high relevance followed timeline item",
                "source": "get_latest_timeline",
                "source_rank": 100,
                "persona_score": 32,
                "priority_score": 100032,
                "persona_hits": ["timeline", "persona"],
                "user": {"screen_name": "example"},
            }
        ]
    try:
        from x_signal import rank_browse_candidates

        return rank_browse_candidates(items)
    except Exception:
        return items


def generate_browse_candidates(
    items: List[Dict[str, Any]],
    max_items: int,
    max_likes: int,
    max_reposts: int,
    max_quotes: int,
) -> List[Candidate]:
    mood = random.choice(MOODS)
    ranked = rank_items(items)
    candidates: List[Candidate] = []
    counts = {"like": 0, "repost": 0, "quote": 0}
    seen_targets: set[str] = set()
    for item in ranked[: max(1, max_items)]:
        target = item_id(item)
        if not target or target in seen_targets:
            continue
        seen_targets.add(target)
        source_rank = int(item.get("source_rank") or 0)
        persona_score = int(item.get("persona_score") or 0)
        hits = item.get("persona_hits") or []
        common = {
            "target": target,
            "screen_name": user_screen_name(item.get("user") or item.get("author")),
            "url": str(item.get("url") or ""),
            "metadata": {
                "source": item.get("source", ""),
                "source_rank": source_rank,
                "persona_score": persona_score,
                "priority_score": item.get("priority_score", 0),
                "persona_hits": hits,
                "mood": mood,
                "browse_text": str(item.get("text") or "")[:240],
            },
        }
        if counts["like"] < max_likes:
            candidates.append(
                Candidate(
                    "like",
                    f"browse selected low-risk relevant item; source_rank={source_rank}; persona_score={persona_score}; mood={mood}",
                    **common,
                )
            )
            counts["like"] += 1
        if source_rank >= 85 and persona_score >= 8 and counts["repost"] < max_reposts:
            candidates.append(
                Candidate(
                    "repost",
                    f"browse selected high-signal item worth boosting; source_rank={source_rank}; persona_score={persona_score}; mood={mood}",
                    **common,
                )
            )
            counts["repost"] += 1
        if (persona_score >= 16 or (source_rank >= 100 and persona_score >= 8)) and counts["quote"] < max_quotes:
            candidates.append(
                Candidate(
                    "quote",
                    f"browse selected item worth persona quote; source_rank={source_rank}; persona_score={persona_score}; mood={mood}",
                    text=quote_text(item, mood),
                    **common,
                )
            )
            counts["quote"] += 1
    return candidates


def generate_candidates(
    kind: str,
    browse_items: List[Dict[str, Any]] = None,
    max_browse_items: int = 3,
    max_browse_likes: int = 3,
    max_browse_reposts: int = 1,
    max_browse_quotes: int = 1,
) -> List[Candidate]:
    mood = random.choice(MOODS)
    if kind == "post":
        return [Candidate("post", f"scheduled original post; mood={mood}", text=f"[draft mood={mood}]")]
    if kind == "browse":
        return generate_browse_candidates(
            browse_items or [],
            max_browse_items,
            max_browse_likes,
            max_browse_reposts,
            max_browse_quotes,
        )
    return []


def feature_enabled(config: Dict[str, Any], kind: str, candidate: Candidate) -> bool:
    features = config.get("features") or {}
    if kind == "browse" and not features.get("browse_timeline", True):
        return False
    feature_key = ACTION_FEATURES.get(candidate.action)
    return bool(features.get(feature_key, True)) if feature_key else True


def audit_candidate(
    admin_api: str,
    admin_token: str,
    candidate: Candidate,
    sent: bool,
    shadow: bool,
    metadata: Dict[str, Any],
) -> None:
    api_json(
        admin_api,
        "/api/audit",
        {
            "action": candidate.action,
            "target": candidate.target,
            "reason": candidate.reason,
            "risk": candidate.risk,
            "text": candidate.text,
            "sent": sent,
            "shadow": shadow,
            "metadata": {**candidate.metadata, **metadata},
        },
        admin_token,
    )


def run_adapter(script_dir: Path, candidate: Candidate, dry_run: bool) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(script_dir / "x_adapter.py"),
        candidate.action,
        "--dry-run" if dry_run else "--adapter",
    ]
    if dry_run:
        cmd.extend(["--adapter", "twikit"])
    else:
        cmd.append("twikit")
    if candidate.text:
        cmd.extend(["--text", candidate.text])
    if candidate.target:
        if candidate.action == "follow":
            cmd.extend(["--user", candidate.target])
        else:
            cmd.extend(["--tweet-id", candidate.target])
    if candidate.screen_name:
        cmd.extend(["--screen-name", candidate.screen_name])
    if candidate.url:
        cmd.extend(["--url", candidate.url])
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"ok": False, "error": proc.stdout, "returncode": proc.returncode}


def main() -> int:
    parser = argparse.ArgumentParser(description="Limited autonomous action runner for OpenClaw Agent Factory.")
    parser.add_argument("--admin-api", default="http://127.0.0.1:18880")
    parser.add_argument("--admin-token", default="")
    parser.add_argument("--kind", choices=["post", "browse"], default="post")
    parser.add_argument("--browse-input", default="", help="JSON list of ranked or unranked timeline candidates.")
    parser.add_argument("--max-browse-items", type=int, default=3)
    parser.add_argument("--max-browse-likes", type=int, default=3)
    parser.add_argument("--max-browse-reposts", type=int, default=1)
    parser.add_argument("--max-browse-quotes", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    config = api_json(args.admin_api, "/api/config", token=args.admin_token)
    features = config.get("features") or {}
    effective_dry_run = args.dry_run or bool(features.get("shadow_mode"))
    candidates = generate_candidates(
        args.kind,
        load_browse_items(args.browse_input),
        args.max_browse_items,
        args.max_browse_likes,
        args.max_browse_reposts,
        args.max_browse_quotes,
    )
    results = []
    for candidate in candidates:
        if not feature_enabled(config, args.kind, candidate):
            skipped = {"ok": False, "reason": "feature_disabled"}
            audit_candidate(args.admin_api, args.admin_token, candidate, sent=False, shadow=effective_dry_run, metadata={"skipped": skipped})
            results.append({"candidate": candidate.__dict__, "skipped": skipped})
            continue
        rate = api_json(args.admin_api, "/api/rate/check", {"action": candidate.action, "increment": True}, args.admin_token)
        if not rate.get("ok"):
            audit_candidate(args.admin_api, args.admin_token, candidate, sent=False, shadow=effective_dry_run, metadata={"skipped": rate})
            results.append({"candidate": candidate.__dict__, "skipped": rate})
            continue
        adapter_result = run_adapter(script_dir, candidate, dry_run=effective_dry_run)
        audit_candidate(
            args.admin_api,
            args.admin_token,
            candidate,
            sent=bool(adapter_result.get("ok") and not effective_dry_run),
            shadow=effective_dry_run or bool(adapter_result.get("dry_run")),
            metadata={"adapter": adapter_result},
        )
        results.append({"candidate": candidate.__dict__, "adapter": adapter_result})
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
