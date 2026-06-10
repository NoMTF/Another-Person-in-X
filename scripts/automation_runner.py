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


BROWSE_REFERENCE_PER_200 = {"like": 15, "repost": 35, "reply": 30, "quote": 10, "follow": 1}
REPOST_TO_LIKE_RATIO = BROWSE_REFERENCE_PER_200["repost"] / BROWSE_REFERENCE_PER_200["like"]
QUOTE_TO_LIKE_RATIO = BROWSE_REFERENCE_PER_200["quote"] / BROWSE_REFERENCE_PER_200["like"]


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


def truthy_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "following", "followed"}:
            return True
        if normalized in {"false", "no", "0", "none", "not_following", "not-following"}:
            return False
    return None


def nested_follow_flag(value: Any, depth: int = 0) -> bool | None:
    if depth > 4 or value is None:
        return None
    if isinstance(value, dict):
        for key, child in value.items():
            key_l = str(key).lower()
            if key_l in {"following", "is_following", "viewer_is_following", "followed_by_viewer"}:
                flag = truthy_flag(child)
                if flag is not None:
                    return flag
            if key_l == "connections" and isinstance(child, list):
                normalized = {str(item).lower() for item in child}
                if "following" in normalized:
                    return True
            if key_l == "relationship" and isinstance(child, str):
                flag = truthy_flag(child)
                if flag is not None:
                    return flag
        for child in value.values():
            flag = nested_follow_flag(child, depth + 1)
            if flag is not None:
                return flag
    if isinstance(value, list):
        normalized = {str(item).lower() for item in value if isinstance(item, str)}
        if "following" in normalized:
            return True
        for child in value[:20]:
            flag = nested_follow_flag(child, depth + 1)
            if flag is not None:
                return flag
    return None


def author_already_followed(item: Dict[str, Any]) -> bool:
    for value in (item.get("user"), item.get("author"), item):
        flag = nested_follow_flag(value)
        if flag is not None:
            return flag
    source = str(item.get("source") or "").lower()
    return any(marker in source for marker in ("get_latest_timeline", "get_timeline", "home_timeline", "followed_timeline"))


def author_is_self(item: Dict[str, Any]) -> bool:
    for key in ("is_self", "own", "owned_by_profile", "self_author"):
        flag = truthy_flag(item.get(key))
        if flag:
            return True
    return False


def author_follow_target(item: Dict[str, Any]) -> str:
    author = item.get("user") or item.get("author") or {}
    if isinstance(author, dict):
        for key in ("id", "id_str", "rest_id", "user_id"):
            value = author.get(key)
            if value:
                return str(value)
        return user_screen_name(author)
    return user_screen_name(author)


def item_id(item: Dict[str, Any]) -> str:
    return str(item.get("id") or item.get("tweet_id") or item.get("id_str") or item.get("rest_id") or "")


def weighted_choice(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    total = sum(max(float(row.get("count") or 0), 0.1) for row in rows)
    cursor = random.random() * total
    for row in rows:
        cursor -= max(float(row.get("count") or 0), 0.1)
        if cursor <= 0:
            return row
    return rows[-1]


def load_style_spectrum(path: str = "") -> Dict[str, Any]:
    candidates = []
    if path:
        candidates.append(Path(path))
    script_dir = Path(__file__).resolve().parent
    candidates.extend(
        [
            script_dir.parent / "data" / "style_spectrum.json",
            script_dir.parent / "style_spectrum.json",
        ]
    )
    for candidate in candidates:
        try:
            if candidate.exists():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def sample_style_spectrum(spectrum: Dict[str, Any], kind: str) -> Dict[str, Any]:
    clusters = list(spectrum.get("clusters") or [])
    rare = list(spectrum.get("rare_but_valid") or [])
    if not clusters:
        return {
            "source": "missing_style_spectrum",
            "kind": kind,
            "sampling_note": "runtime should generate text from the persona skill before sending",
        }
    pool = rare if rare and random.random() < 0.16 else clusters
    cluster = weighted_choice(pool)
    examples = list(cluster.get("examples") or [])
    random.shuffle(examples)
    return {
        "source": "corpus_style_spectrum",
        "kind": kind,
        "cluster_id": cluster.get("id"),
        "features": cluster.get("features") or {},
        "ratio": cluster.get("ratio"),
        "example_anchors": examples[:3],
    }


def repost_limit_for_likes(max_likes: int) -> int:
    if max_likes <= 0:
        return 0
    return max(1, round(max_likes * REPOST_TO_LIKE_RATIO)) if max_likes >= 2 else 1


def quote_limit_for_likes(max_likes: int) -> int:
    if max_likes <= 0:
        return 0
    return max(1, round(max_likes * QUOTE_TO_LIKE_RATIO))


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
        script_dir = Path(__file__).resolve().parent
        if str(script_dir) not in sys.path:
            sys.path.insert(0, str(script_dir))
        from x_signal import rank_browse_candidates

        return rank_browse_candidates(items)
    except Exception:
        return items


def generate_browse_candidates(
    items: List[Dict[str, Any]],
    max_items: int,
    max_likes: int,
    max_reposts: int | None,
    max_quotes: int | None,
    max_follows: int,
    style_spectrum: Dict[str, Any] | None = None,
) -> List[Candidate]:
    ranked = rank_items(items)
    candidates: List[Candidate] = []
    effective_max_reposts = repost_limit_for_likes(max_likes) if max_reposts is None else max_reposts
    effective_max_quotes = quote_limit_for_likes(max_likes) if max_quotes is None else max_quotes
    counts = {"like": 0, "repost": 0, "quote": 0, "follow": 0}
    seen_targets: set[str] = set()
    seen_follow_targets: set[str] = set()
    for item in ranked[: max(1, max_items)]:
        target = item_id(item)
        if not target or target in seen_targets:
            continue
        seen_targets.add(target)
        source_rank = int(item.get("source_rank") or 0)
        persona_score = int(item.get("persona_score") or 0)
        hits = item.get("persona_hits") or []
        style_sample = sample_style_spectrum(style_spectrum or {}, "browse")
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
                "style_sample": style_sample,
                "context_signals": item.get("context_signals") or {},
                "browse_text": str(item.get("text") or "")[:240],
            },
        }
        if counts["like"] < max_likes:
            candidates.append(
                Candidate(
                    "like",
                    f"browse selected low-risk relevant item; source_rank={source_rank}; persona_score={persona_score}",
                    **common,
                )
            )
            counts["like"] += 1
        if (
            source_rank >= 90
            and persona_score >= 16
            and counts["repost"] < effective_max_reposts
        ):
            candidates.append(
                Candidate(
                    "repost",
                    f"browse selected high-signal item worth quiet boosting; source_rank={source_rank}; persona_score={persona_score}; reference_per_200={BROWSE_REFERENCE_PER_200}",
                    **common,
                )
            )
            counts["repost"] += 1
        if (persona_score >= 16 or (source_rank >= 100 and persona_score >= 8)) and counts["quote"] < effective_max_quotes:
            quote_style = sample_style_spectrum(style_spectrum or {}, "quote")
            candidates.append(
                Candidate(
                    "quote",
                    f"browse selected item worth persona quote when the persona generator has something natural to add; source_rank={source_rank}; persona_score={persona_score}; reference_per_200={BROWSE_REFERENCE_PER_200}",
                    text=str(item.get("quote_text") or item.get("draft") or ""),
                    **common,
                )
            )
            candidates[-1].metadata["style_sample"] = quote_style
            candidates[-1].metadata["needs_persona_generation"] = not bool(candidates[-1].text.strip())
            counts["quote"] += 1
        follow_target = author_follow_target(item)
        should_follow = (
            follow_target
            and follow_target not in seen_follow_targets
            and counts["follow"] < max_follows
            and source_rank >= 55
            and persona_score >= 16
            and not author_already_followed(item)
            and not author_is_self(item)
        )
        if should_follow:
            seen_follow_targets.add(follow_target)
            candidates.append(
                Candidate(
                    "follow",
                    f"browse discovered high-relevance author worth following; source_rank={source_rank}; persona_score={persona_score}",
                    target=follow_target,
                    screen_name=common["screen_name"],
                    url=common["url"],
                    metadata={
                        **common["metadata"],
                        "tweet_id": target,
                        "follow_screen_name": common["screen_name"],
                    },
                )
            )
            counts["follow"] += 1
    return candidates


def generate_candidates(
    kind: str,
    browse_items: List[Dict[str, Any]] = None,
    max_browse_items: int = 3,
    max_browse_likes: int = 3,
    max_browse_reposts: int | None = None,
    max_browse_quotes: int | None = None,
    max_browse_follows: int = 1,
    style_spectrum: Dict[str, Any] | None = None,
) -> List[Candidate]:
    if kind == "post":
        style_sample = sample_style_spectrum(style_spectrum or {}, "post")
        return [
            Candidate(
                "post",
                "scheduled original post requires persona generation before send",
                metadata={"style_sample": style_sample, "needs_persona_generation": True},
            )
        ]
    if kind == "browse":
        return generate_browse_candidates(
            browse_items or [],
            max_browse_items,
            max_browse_likes,
            max_browse_reposts,
            max_browse_quotes,
            max_browse_follows,
            style_spectrum,
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
    if candidate.action in {"post", "reply", "quote"} and not candidate.text.strip():
        return {
            "ok": False,
            "dry_run": dry_run,
            "error": "missing persona-generated text; skip send",
            "metadata": {"needs_persona_generation": True},
        }
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
    parser.add_argument(
        "--max-browse-reposts",
        type=int,
        default=None,
        help="Defaults from the browse reference mix: about 35 reposts per 15 likes.",
    )
    parser.add_argument(
        "--max-browse-quotes",
        type=int,
        default=None,
        help="Defaults from the browse reference mix: about 10 quotes per 15 likes.",
    )
    parser.add_argument("--max-browse-follows", type=int, default=1)
    parser.add_argument("--style-spectrum", default="", help="Optional persona data/style_spectrum.json path.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    config = api_json(args.admin_api, "/api/config", token=args.admin_token)
    features = config.get("features") or {}
    effective_dry_run = args.dry_run or bool(features.get("shadow_mode"))
    style_spectrum = load_style_spectrum(args.style_spectrum)
    candidates = generate_candidates(
        args.kind,
        load_browse_items(args.browse_input),
        args.max_browse_items,
        args.max_browse_likes,
        args.max_browse_reposts,
        args.max_browse_quotes,
        args.max_browse_follows,
        style_spectrum,
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
