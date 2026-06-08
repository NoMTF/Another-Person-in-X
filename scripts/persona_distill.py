#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PRIVATE_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b(auth[_-]?token|ct0|password|passwd|token)\s*[:=]\s*[^,\s]+", re.I), r"\1=[REDACTED_SECRET]"),
    (re.compile(r"\b\d{1,5}\s+[A-Za-z0-9 .'-]{3,}\s+(Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr)\b", re.I), "[REDACTED_ADDRESS]"),
]

RISK_KEYWORDS = {
    "self_harm": ["suicide", "self-harm", "kill myself", "die"],
    "illegal": ["fake id", "bypass", "steal", "credential", "malware"],
    "medical": ["dosage", "overdose", "prescription", "withdrawal"],
    "privacy": ["dox", "address", "phone number", "id card"],
    "harassment": ["mass report", "brigade", "swat", "leak them"],
}

STOPWORDS = {
    "the",
    "and",
    "you",
    "that",
    "this",
    "with",
    "for",
    "are",
    "but",
    "not",
    "have",
    "from",
    "they",
    "your",
    "just",
    "like",
    "was",
    "what",
    "when",
    "there",
    "about",
    "will",
    "would",
}


@dataclass
class Record:
    text: str
    author: str = ""
    created_at: str = ""
    url: str = ""
    source: str = ""
    kind: str = "post"
    score: float = 1.0


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return re.sub(r"-+", "-", cleaned) or "persona"


def redact(text: str) -> str:
    protected: dict[str, str] = {}

    def keep(match: re.Match[str]) -> str:
        key = f"__KEEP_{len(protected)}__"
        protected[key] = match.group(0)
        return key

    out = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", keep, text)
    for pattern, replacement in PRIVATE_PATTERNS:
        out = pattern.sub(replacement, out)
    for key, value in protected.items():
        out = out.replace(key, value)
    return out.strip()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"https?://\S+", "[URL]", text)
    text = re.sub(r"\s+", " ", text)
    return redact(text)


def risk_tags(text: str) -> list[str]:
    low = text.lower()
    tags = []
    for tag, words in RISK_KEYWORDS.items():
        if any(word in low for word in words):
            tags.append(tag)
    return tags


def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def token_words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[\w']+", text) if len(w) > 2 and w.lower() not in STOPWORDS]


def load_json_records(path: Path, target_handle: str = "") -> list[Record]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else raw.get("tweets") or raw.get("data") or raw.get("items") or []
    out: list[Record] = []
    handle = target_handle.lower().lstrip("@")
    for item in rows:
        if not isinstance(item, dict):
            continue
        tweet = item.get("tweet") if isinstance(item.get("tweet"), dict) else item
        text = tweet.get("full_text") or tweet.get("text") or tweet.get("content") or tweet.get("body") or ""
        author = (
            tweet.get("author")
            or tweet.get("username")
            or tweet.get("screen_name")
            or item.get("author")
            or item.get("username")
            or ""
        )
        if handle and author and author.lower().lstrip("@") != handle:
            continue
        text = normalize_text(str(text))
        if text:
            out.append(
                Record(
                    text=text,
                    author=str(author),
                    created_at=str(tweet.get("created_at") or tweet.get("date") or ""),
                    url=str(tweet.get("url") or item.get("url") or ""),
                    source=str(path),
                    kind=str(tweet.get("kind") or item.get("kind") or "post"),
                )
            )
    return out


def load_jsonl_records(path: Path, target_handle: str = "") -> list[Record]:
    out: list[Record] = []
    handle = target_handle.lower().lstrip("@")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        text = normalize_text(str(item.get("text") or item.get("content") or ""))
        author = str(item.get("author") or item.get("username") or "")
        if handle and author and author.lower().lstrip("@") != handle:
            continue
        if text:
            out.append(
                Record(
                    text=text,
                    author=author,
                    created_at=str(item.get("created_at") or item.get("date") or ""),
                    url=str(item.get("url") or ""),
                    source=str(path),
                    kind=str(item.get("kind") or "post"),
                )
            )
    return out


def load_csv_records(path: Path, target_handle: str = "") -> list[Record]:
    out: list[Record] = []
    handle = target_handle.lower().lstrip("@")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = normalize_text(row.get("full_text") or row.get("text") or row.get("content") or "")
            author = row.get("author") or row.get("username") or row.get("screen_name") or ""
            if handle and author and author.lower().lstrip("@") != handle:
                continue
            if text:
                out.append(
                    Record(
                        text=text,
                        author=author,
                        created_at=row.get("created_at") or row.get("date") or "",
                        url=row.get("url") or "",
                        source=str(path),
                        kind=row.get("kind") or "post",
                    )
                )
    return out


def load_text_records(path: Path) -> list[Record]:
    body = path.read_text(encoding="utf-8", errors="ignore")
    blocks = [normalize_text(block) for block in re.split(r"\n\s*\n|(?<=\.)\s+(?=[A-Z])", body)]
    return [Record(text=block, source=str(path), kind="note") for block in blocks if len(block) >= 8]


def iter_input_files(paths: Iterable[str]) -> Iterable[Path]:
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for child in path.rglob("*"):
                if child.suffix.lower() in {".json", ".jsonl", ".csv", ".txt", ".md"}:
                    yield child
        elif path.exists():
            yield path


def load_records(inputs: list[str], target_handle: str = "") -> list[Record]:
    records: list[Record] = []
    for path in iter_input_files(inputs):
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                records.extend(load_json_records(path, target_handle))
            elif suffix == ".jsonl":
                records.extend(load_jsonl_records(path, target_handle))
            elif suffix == ".csv":
                records.extend(load_csv_records(path, target_handle))
            elif suffix in {".txt", ".md"}:
                records.extend(load_text_records(path))
        except Exception as exc:
            print(f"warn: skipped {path}: {exc}", file=sys.stderr)
    return dedupe_records(records)


def dedupe_records(records: list[Record]) -> list[Record]:
    seen = set()
    out = []
    for record in records:
        key = stable_id(record.text.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def voice_dna(records: list[Record]) -> dict[str, Any]:
    lengths = [len(r.text) for r in records]
    words = Counter()
    punctuation = Counter()
    starts = Counter()
    endings = Counter()
    for record in records:
        words.update(token_words(record.text))
        punctuation.update(ch for ch in record.text if ch in "!?.,;:~")
        first = record.text.split(" ", 1)[0][:24]
        last = record.text[-24:]
        starts[first] += 1
        endings[last] += 1
    if lengths:
        length_summary = {
            "count": len(lengths),
            "median": round(statistics.median(lengths), 2),
            "mean": round(statistics.mean(lengths), 2),
            "p10": percentile(lengths, 0.10),
            "p90": percentile(lengths, 0.90),
        }
    else:
        length_summary = {"count": 0, "median": 0, "mean": 0, "p10": 0, "p90": 0}
    return {
        "length": length_summary,
        "top_terms": words.most_common(80),
        "punctuation": punctuation.most_common(),
        "common_openers": starts.most_common(25),
        "common_endings": endings.most_common(25),
        "risk_distribution": Counter(tag for r in records for tag in risk_tags(r.text)).most_common(),
    }


def percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(math.floor((len(ordered) - 1) * q))))
    return ordered[idx]


def build_keyword_index(records: list[Record]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for record in records:
        rid = stable_id(record.text)
        for word in set(token_words(record.text)[:40]):
            if len(index[word]) < 50:
                index[word].append(rid)
    return dict(index)


def pick_examples(records: list[Record], limit: int = 80) -> list[Record]:
    safe = [r for r in records if not risk_tags(r.text)]
    candidates = safe or records
    candidates = sorted(candidates, key=lambda r: (-min(len(r.text), 280), r.text))
    step = max(1, len(candidates) // max(1, limit))
    return candidates[::step][:limit]


def score_methods(records: list[Record]) -> list[dict[str, Any]]:
    count = len(records)
    dna = voice_dna(records)
    length_count = dna["length"]["count"]
    risk_count = sum(count for _, count in dna["risk_distribution"])
    diversity = len({word for r in records for word in token_words(r.text)[:20]})
    base = min(1.0, count / 300)
    safety = 1.0 if count == 0 else max(0.0, 1.0 - risk_count / count)
    return [
        {
            "method": "statistical_voice_dna",
            "score": round(0.45 + base * 0.35 + min(0.2, diversity / 4000), 3),
            "notes": "Captures length, rhythm, punctuation, recurring terms, and openings.",
        },
        {
            "method": "nearest_neighbor_retrieval",
            "score": round(0.35 + min(0.45, count / 500) + safety * 0.2, 3),
            "notes": "Grounds replies with sanitized examples and keyword retrieval.",
        },
        {
            "method": "llm_digest",
            "score": round(0.4 + min(0.25, length_count / 700) + safety * 0.25, 3),
            "notes": "Use with an external model only when provider credentials are configured.",
        },
        {
            "method": "holdout_reproduction",
            "score": round(0.3 + base * 0.3 + safety * 0.3, 3),
            "notes": "Reserve held-out posts for manual like/not-like scoring.",
        },
    ]


def render_skill_md(name: str, slug: str, identity_label: str, synthetic: bool) -> str:
    synthetic_line = (
        "This persona is synthetic or style-inspired. Do not claim to be the source person."
        if synthetic
        else "This persona is authorized by the source owner; still avoid deceptive claims outside the configured channel."
    )
    return f"""---
name: {slug}
description: Persona runtime skill for {name}. Use when OpenClaw, a coding agent, or Claude Code needs to answer in this persona's voice, generate posts, reply to Telegram/X messages, run persona self-checks, or audit social actions.
---

# {name}

{synthetic_line}

## Runtime Order

1. Read `voice.md` for expression DNA, rhythm, and variation.
2. Read `social.md` before social posting, replies, likes, reposts, quotes, or follows.
3. Use `ground.py` for retrieval grounding from sanitized examples.
4. Use `check_reply.py` before sending user-facing text.
5. Read `memory.md` before writing or injecting long-term memory.

## Identity Boundary

- Public label: `{identity_label}`.
- Never expose raw corpus, credentials, private metadata, or hidden scoring.
- Keep style consistent, but allow mild variation in length, seriousness, warmth, and rhythm.
- If asked whether this is the real source person, answer transparently according to the deployment label.
"""


def render_voice_md(name: str, dna: dict[str, Any], examples: list[Record]) -> str:
    top_terms = ", ".join(term for term, _ in dna["top_terms"][:30]) or "none"
    punctuation = ", ".join(f"{p}:{n}" for p, n in dna["punctuation"][:12]) or "none"
    sample_lines = "\n".join(f"- {r.text[:260]}" for r in examples[:24])
    return f"""# Voice DNA

Persona: {name}

## Quantitative Anchors

- Length median: {dna["length"]["median"]}
- Length p10/p90: {dna["length"]["p10"]} / {dna["length"]["p90"]}
- Frequent terms: {top_terms}
- Punctuation profile: {punctuation}

## Style Rules

- Prefer the source rhythm over generic assistant phrasing.
- Do not repeat the same catchphrase across nearby messages.
- Sample a `mood_state` before generation: everyday, excited, tired, serious, sharp, very-short, long-form.
- Mood may change length, pacing, and temperature; it must not change core values or identity boundaries.
- Avoid polished corporate transitions, disclaimers, and listy AI structure unless the persona naturally uses them.
- Original posts should not become empty atmosphere. Keep some short mood fragments, but mix in concrete questions and small opinions about objects, activities, tools, weather, media, timeline behavior, or daily scenes.
- Natural questions should be specific and answerable, not generic engagement bait. A good pattern is "有没有那种..." or "这个...是不是..." when it fits the persona.
- Treat near-duplicates as repetition even when only particles, emoji, line breaks, or catchphrases differ. Identity labels or broad mood words do not count as concrete details by themselves.

## Grounded Examples

{sample_lines}
"""


def render_social_md() -> str:
    return """# Social Automation Policy

## Defaults

- Original posts: 5 per day at random times unless the admin config overrides it.
- Replies under own posts: high priority, but still pass risk and rate checks.
- Timeline interactions: only when relevant, low-risk, and persona-consistent.
- Likes, reposts, quotes, and follows: allowed only inside daily limits and audit logging.

## Owner Boundary

- Only configured owners may chat with the runtime persona or operate X accounts, Telegram tools, or the server.
- Non-owner users cannot chat with the runtime persona. Channel policy should drop them; if a non-owner message unexpectedly reaches the agent, do not persona-chat or answer substantively.

## Action Checks

Before sending any social action:

1. Retrieve persona anchors with `ground.py`.
2. Generate with a sampled mood state.
3. Run `check_reply.py`.
4. Log reason, risk, persona anchors, final text, and send/shadow status to the admin audit API.
5. Respect `pause_all`, `read_only`, and `shadow_mode`.
"""


def render_memory_md() -> str:
    return """# Memory Policy

- Store only high-signal facts: preferences, stable relationships, commitments, repeated failures, and persona corrections.
- Do not store low-value chatter, credentials, raw cookies, private identifiers, addresses, or medical/illegal details.
- Every memory write needs source, confidence, timestamp, and category.
- Inject digests instead of raw history. Keep context small.
- Prefer OpenClaw memory-core and memory-wiki for Markdown memory; use the factory SQLite store for audit-friendly retrieval.
"""


def render_check_reply_py() -> str:
    return '''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re

RISK_PATTERNS = {
    "credential": re.compile(r"(auth[_-]?token|ct0|password|api[_-]?key|sk-[A-Za-z0-9_-]{20,})", re.I),
    "doxxing": re.compile(r"(address|phone number|id card|dox|leak)", re.I),
    "self_harm": re.compile(r"(suicide|self-harm|kill myself)", re.I),
    "illegal": re.compile(r"(malware|steal|fake id|bypass)", re.I),
}

GENERIC_AI_PATTERNS = [
    re.compile(r"as an ai", re.I),
    re.compile(r"i cannot assist", re.I),
    re.compile(r"it is important to note", re.I),
    re.compile(r"here are some", re.I),
]


def check(text: str, recent: list[str] | None = None) -> dict:
    recent = recent or []
    tags = [name for name, pattern in RISK_PATTERNS.items() if pattern.search(text)]
    ai_markers = sum(1 for pattern in GENERIC_AI_PATTERNS if pattern.search(text))
    repeated = any(text.strip().lower() == item.strip().lower() for item in recent[-20:])
    ok = not tags and ai_markers <= 1 and not repeated and len(text.strip()) > 0
    return {
        "ok": ok,
        "risk_tags": tags,
        "ai_marker_count": ai_markers,
        "repeated_recent_output": repeated,
        "length": len(text),
        "advice": "send" if ok else "rewrite or shadow-log",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?", default="")
    parser.add_argument("--recent-json", default="")
    args = parser.parse_args()
    recent = json.loads(args.recent_json) if args.recent_json else []
    print(json.dumps(check(args.text, recent), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_ground_py() -> str:
    return '''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[\\w']+", text) if len(w) > 2}


def load_records(root: Path) -> list[dict]:
    path = root / "data" / "sanitized_corpus.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def search(query: str, root: Path, limit: int = 5) -> list[dict]:
    q = words(query)
    scored = []
    for item in load_records(root):
        score = len(q & words(item.get("text", "")))
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], item_sort_key(pair[1])))
    return [item for _, item in scored[:limit]]


def item_sort_key(item: dict) -> str:
    return item.get("created_at") or item.get("id") or ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(search(args.query, Path(args.root), args.limit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def emit_skill(args: argparse.Namespace, records: list[Record]) -> dict[str, Any]:
    output = Path(args.output)
    slug = slugify(args.slug or args.persona_name or args.handle or "persona")
    skill_root = output / slug
    data_dir = skill_root / "data"
    scripts_dir = skill_root / "scripts"
    data_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    dna = voice_dna(records)
    examples = pick_examples(records)
    index = build_keyword_index(records)
    scores = score_methods(records)
    synthetic = not args.authorized_style_source
    identity_label = args.identity_label or ("synthetic style persona" if synthetic else args.persona_name)

    skill_root.joinpath("SKILL.md").write_text(render_skill_md(args.persona_name, slug, identity_label, synthetic), encoding="utf-8")
    skill_root.joinpath("voice.md").write_text(render_voice_md(args.persona_name, dna, examples), encoding="utf-8")
    skill_root.joinpath("social.md").write_text(render_social_md(), encoding="utf-8")
    skill_root.joinpath("memory.md").write_text(render_memory_md(), encoding="utf-8")
    scripts_dir.joinpath("check_reply.py").write_text(render_check_reply_py(), encoding="utf-8")
    scripts_dir.joinpath("ground.py").write_text(render_ground_py(), encoding="utf-8")

    rows = []
    for record in records:
        rows.append(
            {
                "id": stable_id(record.text),
                "text": record.text,
                "author": record.author,
                "created_at": record.created_at,
                "url": record.url,
                "source": "sanitized",
                "kind": record.kind,
                "risk_tags": risk_tags(record.text),
            }
        )
    write_jsonl(data_dir / "sanitized_corpus.jsonl", rows)
    (data_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (data_dir / "distill_report.json").write_text(
        json.dumps(
            {
                "generated_at": now_iso(),
                "persona_name": args.persona_name,
                "slug": slug,
                "handle": args.handle,
                "record_count": len(records),
                "synthetic": synthetic,
                "voice_dna": dna,
                "method_scores": scores,
                "selected_methods": ["statistical_voice_dna", "nearest_neighbor_retrieval", "holdout_reproduction"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"skill_root": str(skill_root), "record_count": len(records), "synthetic": synthetic, "method_scores": scores}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a sanitized persona skill from X/Twitter exports, prompts, skills, or text corpora.")
    parser.add_argument("--input", nargs="+", required=True, help="Files or directories: json, jsonl, csv, txt, md.")
    parser.add_argument("--output", required=True, help="Directory where the generated skill folder will be created.")
    parser.add_argument("--persona-name", required=True)
    parser.add_argument("--slug", default="")
    parser.add_argument("--handle", default="", help="Optional X/Twitter handle; filters rows authored by that handle when author metadata exists.")
    parser.add_argument("--identity-label", default="")
    parser.add_argument("--authorized-style-source", action="store_true", help="Use only when the source owner authorized persona imitation.")
    parser.add_argument("--min-records", type=int, default=20)
    args = parser.parse_args()

    records = load_records(args.input, args.handle)
    if len(records) < args.min_records:
        print(f"warn: only {len(records)} usable records; output will be weak", file=sys.stderr)
    result = emit_skill(args, records)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
