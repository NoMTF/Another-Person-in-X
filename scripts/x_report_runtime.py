#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import sqlite3
import time
import urllib.parse
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4


REPORT_STATUSES = {
    "dry_run",
    "queued",
    "running",
    "needs_owner_confirm",
    "needs_details",
    "needs_manual",
    "succeeded",
    "failed",
    "duplicate_skipped",
    "rate_limited",
}

POST_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:x|twitter)\.com/(?P<screen_name>[A-Za-z0-9_]{1,20}|i/web|i)/status/(?P<tweet_id>\d+)",
    re.I,
)
USER_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:x|twitter)\.com/(?P<screen_name>[A-Za-z0-9_]{1,20})(?:[/?#].*)?$", re.I)
TYPE_SUFFIX_RE = re.compile(r"\{(?P<code>\d{1,3})\}\s*$")


@dataclass(frozen=True)
class ReportType:
    code: int
    slug: str
    label: str
    post_path: tuple[str, ...] = ()
    user_path: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    one_step_submit: bool = False
    force_media_entry: bool = False


REPORT_TYPES: dict[int, ReportType] = {
    1: ReportType(
        1,
        "child_sexual_exploitation",
        "儿童性剥削",
        post_path=("SensitiveMediaOption", "ChildSexualExploitationOption"),
        user_path=("AbuseOption",),
        aliases=("cse", "child", "child_safety", "儿童安全", "儿童性剥削", "恋童", "未成年色情"),
        one_step_submit=True,
        force_media_entry=True,
    ),
    2: ReportType(2, "spam_scam", "垃圾/诈骗", post_path=("SpamOption",), user_path=("SpamOption",), aliases=("spam", "scam", "fraud", "垃圾", "诈骗")),
    3: ReportType(
        3,
        "harassment",
        "骚扰",
        post_path=("AbuseOption", "HarassmentOption", "TargetingSomeoneElseOption"),
        user_path=("AbuseOption",),
        aliases=("harassment", "abuse", "骚扰", "辱骂"),
    ),
    4: ReportType(
        4,
        "hate",
        "仇恨",
        post_path=("AbuseOption", "HateOption", "TargetingGroupOption"),
        user_path=("AbuseOption",),
        aliases=("hate", "仇恨", "歧视"),
    ),
    5: ReportType(
        5,
        "violent_threat",
        "暴力威胁",
        post_path=("AbuseOption", "ViolenceOption", "YesOption"),
        user_path=("AbuseOption",),
        aliases=("violent", "violence", "threat", "威胁", "暴力"),
    ),
    6: ReportType(6, "private_info", "隐私/开盒", post_path=("AbuseOption", "PrivateInfoOption"), user_path=("AbuseOption",), aliases=("privacy", "dox", "doxxing", "隐私", "开盒")),
    7: ReportType(7, "self_harm_intent", "自伤自杀意图", post_path=("SelfHarmOption",), user_path=("SelfHarmOption",), aliases=("self_harm", "suicide", "自伤", "自杀")),
    8: ReportType(8, "encouraging_self_harm", "鼓励自伤", post_path=("AbuseOption", "EncouragingSelfHarmOption"), user_path=("SelfHarmOption",), aliases=("encouraging_self_harm", "教唆自伤")),
    9: ReportType(
        9,
        "nonconsensual_intimate_media",
        "未授权私密媒体",
        post_path=("SensitiveMediaOption", "UnauthorizedPhotoVideoOption", "UnauthorizedIntimateOption", "TargetingSomeoneElseOption"),
        user_path=("SensitiveMediaOption",),
        aliases=("nonconsensual", "intimate", "私密照", "偷拍"),
        force_media_entry=True,
    ),
    10: ReportType(10, "adult_sensitive_media", "成人敏感媒体", post_path=("SensitiveMediaOption", "AdultOption"), user_path=("SensitiveMediaOption",), aliases=("adult", "成人", "色情"), force_media_entry=True),
    11: ReportType(11, "violent_media", "暴力媒体", post_path=("SensitiveMediaOption", "ViolentOption"), user_path=("SensitiveMediaOption",), aliases=("graphic", "bloody", "血腥"), force_media_entry=True),
    12: ReportType(12, "hateful_media", "仇恨媒体", post_path=("SensitiveMediaOption", "HatefulOption"), user_path=("SensitiveMediaOption",), aliases=("hateful_media", "仇恨图片"), force_media_entry=True),
    13: ReportType(13, "impersonation", "冒充", post_path=(), user_path=("ImpersonationOption",), aliases=("impersonation", "冒充", "假冒")),
    14: ReportType(14, "hacked_account", "账号被盗", post_path=(), user_path=("HackedAccountOption",), aliases=("hacked", "盗号", "被盗")),
}

ALIAS_TO_CODE: dict[str, int] = {}
for item in REPORT_TYPES.values():
    ALIAS_TO_CODE[str(item.code)] = item.code
    ALIAS_TO_CODE[item.slug.lower()] = item.code
    ALIAS_TO_CODE[item.label.lower()] = item.code
    for alias in item.aliases:
        ALIAS_TO_CODE[alias.lower()] = item.code


@dataclass
class ParsedTarget:
    raw_url: str
    normalized_url: str
    target_kind: str
    screen_name: str = ""
    tweet_id: str = ""
    type_code: int | None = None


class ReportFlowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_button = False
        self.current_button: dict[str, Any] | None = None
        self.buttons: list[dict[str, Any]] = []
        self.inputs: list[dict[str, str]] = []
        self.forms: list[dict[str, str]] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "button":
            self.in_button = True
            self.current_button = {"attrs": attrs_dict, "text": []}
        elif tag == "input":
            self.inputs.append(attrs_dict)
        elif tag == "textarea":
            self.inputs.append(attrs_dict | {"type": "textarea"})
        elif tag == "form":
            self.forms.append(attrs_dict)

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self.in_button and self.current_button is not None:
            text = re.sub(r"\s+", " ", " ".join(self.current_button["text"])).strip()
            self.current_button["text"] = text
            self.buttons.append(self.current_button)
            self.in_button = False
            self.current_button = None

    def handle_data(self, data: str) -> None:
        if self.in_button and self.current_button is not None:
            self.current_button["text"].append(data)
        if data.strip():
            self.text_parts.append(data.strip())

    @property
    def clean_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.text_parts)).strip()

    @property
    def title(self) -> str:
        return ""


def report_types_payload() -> dict[str, Any]:
    return {
        "types": [
            {
                "code": item.code,
                "slug": item.slug,
                "label": item.label,
                "post_path": list(item.post_path),
                "user_path": list(item.user_path),
                "one_step_submit": item.one_step_submit,
                "force_media_entry": item.force_media_entry,
                "aliases": list(item.aliases),
            }
            for item in REPORT_TYPES.values()
        ]
    }


def normalize_type(value: Any) -> ReportType:
    if value is None or str(value).strip() == "":
        raise ValueError("missing report type code; use /report_types")
    key = str(value).strip().lower().replace("-", "_")
    if key not in ALIAS_TO_CODE:
        raise ValueError(f"unsupported report type: {value}; use /report_types")
    return REPORT_TYPES[ALIAS_TO_CODE[key]]


def parse_target_url(value: str, explicit_type: Any = None) -> ParsedTarget:
    raw = str(value or "").strip()
    match = TYPE_SUFFIX_RE.search(raw)
    suffix_code = int(match.group("code")) if match else None
    if match:
        raw = raw[: match.start()].strip()
    type_code = suffix_code
    if explicit_type not in (None, ""):
        key = str(explicit_type).strip().lower().replace("-", "_")
        type_code = int(key) if re.fullmatch(r"\d{1,3}", key) else ALIAS_TO_CODE.get(key)

    post_match = POST_URL_RE.match(raw)
    if post_match:
        screen = post_match.group("screen_name")
        tweet_id = post_match.group("tweet_id")
        normalized = f"https://x.com/{screen}/status/{tweet_id}"
        return ParsedTarget(raw, normalized, "post", "" if screen.lower() in {"i", "i/web"} else screen, tweet_id, type_code)

    user_match = USER_URL_RE.match(raw)
    if user_match:
        screen = user_match.group("screen_name")
        return ParsedTarget(raw, f"https://x.com/{screen}", "user", screen, "", type_code)

    screen = raw.lstrip("@").strip()
    if re.fullmatch(r"[A-Za-z0-9_]{1,20}", screen):
        return ParsedTarget(raw, f"https://x.com/{screen}", "user", screen, "", type_code)

    raise ValueError("report target must be an X post URL, X user URL, or @handle")


def legacy_target_url(payload: dict[str, Any]) -> str:
    if payload.get("target_url"):
        return str(payload["target_url"])
    if payload.get("tweet_id"):
        screen = str(payload.get("screen_name") or "i").strip().lstrip("@") or "i"
        return f"https://x.com/{screen}/status/{payload['tweet_id']}"
    if payload.get("screen_name"):
        return f"https://x.com/{str(payload['screen_name']).strip().lstrip('@')}"
    if payload.get("user_id"):
        return str(payload["user_id"])
    raise ValueError("Provide target_url, tweet_id, screen_name, or user_id")


def path_for_scope(report_type: ReportType, action_kind: str) -> tuple[str, ...]:
    if action_kind == "post":
        return report_type.post_path or report_type.user_path
    return report_type.user_path or report_type.post_path


def plan_actions(parsed: ParsedTarget, report_type: ReportType, scope: str = "auto") -> list[dict[str, Any]]:
    scope = (scope or "auto").strip().lower()
    if scope == "auto":
        scope = "both" if parsed.target_kind == "post" else "user"
    if parsed.target_kind == "user" and scope in {"post", "both"}:
        scope = "user"
    if scope not in {"post", "user", "both"}:
        raise ValueError("scope must be auto, post, user, or both")

    kinds = ["post", "user"] if scope == "both" else [scope]
    actions: list[dict[str, Any]] = []
    for kind in kinds:
        path = path_for_scope(report_type, kind)
        if not path:
            raise ValueError(f"report type {report_type.code} has no {kind} path")
        source = "reporttweet" if kind == "post" else "reportprofile"
        actions.append(
            {
                "action_kind": kind,
                "source": source,
                "path": list(path),
                "force_media_entry": kind == "post" and report_type.force_media_entry,
                "one_step_submit": report_type.one_step_submit and kind == "post",
            }
        )
    return actions


def build_plan(payload: dict[str, Any], username: str) -> dict[str, Any]:
    target_url = legacy_target_url(payload)
    parsed = parse_target_url(target_url, payload.get("type_code"))
    if parsed.type_code is None and payload.get("reason"):
        parsed.type_code = ALIAS_TO_CODE.get(str(payload.get("reason")).strip().lower().replace("-", "_"))
    report_type = normalize_type(parsed.type_code)
    actions = plan_actions(parsed, report_type, str(payload.get("scope") or "auto"))
    return {
        "username": username,
        "target_url": parsed.raw_url,
        "normalized_url": parsed.normalized_url,
        "target_kind": parsed.target_kind,
        "screen_name": parsed.screen_name,
        "tweet_id": parsed.tweet_id,
        "type_code": report_type.code,
        "resolved_type": report_type.slug,
        "label": report_type.label,
        "scope": str(payload.get("scope") or "auto"),
        "actions": actions,
        "requires_live_confirm": any(action.get("one_step_submit") for action in actions),
    }


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def title_from_html(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
    return html.unescape(re.sub(r"\s+", " ", match.group(1)).strip()) if match else ""


def parse_report_html(text: str) -> ReportFlowParser:
    parser = ReportFlowParser()
    parser.feed(text)
    return parser


def hidden_value(parser: ReportFlowParser, name: str) -> str:
    for item in parser.inputs:
        if item.get("name") == name:
            return item.get("value", "")
    return ""


def selected_options(parser: ReportFlowParser) -> set[str]:
    values: set[str] = set()
    for button in parser.buttons:
        attrs = button.get("attrs") or {}
        if attrs.get("name") == "selected_option" and attrs.get("value"):
            values.add(str(attrs["value"]))
    return values


def required_inputs(parser: ReportFlowParser) -> list[str]:
    names: list[str] = []
    for item in parser.inputs:
        name = str(item.get("name") or "")
        klass = str(item.get("class") or "")
        if not name or name in {"context", "report_flow_state", "authenticity_token", "csrf_token"}:
            continue
        if "required" in item or "required" in klass or name in {"reporter_email", "signature_input"}:
            names.append(name)
    return names


def form_params_from_parser(parser: ReportFlowParser, option: str) -> dict[str, str]:
    state = hidden_value(parser, "report_flow_state")
    if not state:
        raise RuntimeError("report flow state missing")
    return {
        "context": hidden_value(parser, "context"),
        "report_flow_state": state,
        "lang": hidden_value(parser, "lang") or "zh-cn",
        "is_mobile": hidden_value(parser, "is_mobile") or "true",
        "next_view": hidden_value(parser, "next_view") or "default",
        "selected_option": option,
    }


class ReportQueue:
    def __init__(
        self,
        root: Path,
        username: str,
        audit_file: Path,
        live_enabled: bool,
        client_factory: Callable[[], Any],
        user_id_resolver: Callable[[Any, str], Any],
        http_get: Callable[[str], Any],
        max_concurrency: int = 5,
        min_live_interval_seconds: int = 60,
    ) -> None:
        self.root = root
        self.username = username
        self.audit_file = audit_file
        self.live_enabled = live_enabled
        self.client_factory = client_factory
        self.user_id_resolver = user_id_resolver
        self.http_get = http_get
        self.max_concurrency = max(1, max_concurrency)
        self.min_live_interval_seconds = max(1, min_live_interval_seconds)
        self.db_path = root / "report_queue.sqlite3"
        self._worker_started = False
        self.init_db()

    def init_db(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS report_tasks (
                    id TEXT PRIMARY KEY,
                    account TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    normalized_url TEXT NOT NULL,
                    type_code INTEGER NOT NULL,
                    resolved_type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dry_run INTEGER NOT NULL,
                    confirm TEXT NOT NULL,
                    details TEXT NOT NULL,
                    force INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    locked_at INTEGER,
                    finished_at INTEGER,
                    result_json TEXT,
                    last_error TEXT
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_report_tasks_status ON report_tasks(status, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_report_tasks_duplicate ON report_tasks(account, normalized_url, type_code, created_at)")

    def append_audit(self, event: dict[str, Any]) -> None:
        clean = {key: value for key, value in event.items() if key not in {"auth_token", "ct0", "token", "confirm"}}
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": int(time.time()), "ts_utc": utc_now(), **clean}, ensure_ascii=False, sort_keys=True) + "\n")

    def duplicate_recent(self, plan: dict[str, Any], force: bool) -> dict[str, Any] | None:
        if force:
            return None
        cutoff = int(time.time()) - 24 * 3600
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                """
                SELECT id, status, created_at FROM report_tasks
                WHERE account = ? AND normalized_url = ? AND type_code = ? AND created_at >= ?
                  AND status IN ('queued', 'running', 'succeeded')
                ORDER BY created_at DESC LIMIT 1
                """,
                (self.username, plan["normalized_url"], plan["type_code"], cutoff),
            ).fetchone()
        if not row:
            return None
        return {"id": row[0], "status": row[1], "created_at": row[2]}

    def enqueue(self, payload: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        force = bool(payload.get("force"))
        duplicate = self.duplicate_recent(plan, force)
        if duplicate:
            result = {"ok": True, "sent": False, "status": "duplicate_skipped", "duplicate": duplicate, **plan}
            self.append_audit({"action": "report", "status": "duplicate_skipped", "sent": False, "plan": plan, "duplicate": duplicate})
            return result

        task_id = str(uuid4())
        now = int(time.time())
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                INSERT INTO report_tasks (
                    id, account, target_url, normalized_url, type_code, resolved_type, scope,
                    payload_json, plan_json, status, dry_run, confirm, details, force,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    self.username,
                    plan["target_url"],
                    plan["normalized_url"],
                    plan["type_code"],
                    plan["resolved_type"],
                    str(payload.get("scope") or "auto"),
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(plan, ensure_ascii=False),
                    str(payload.get("confirm") or ""),
                    str(payload.get("details") or ""),
                    1 if force else 0,
                    now,
                    now,
                ),
            )
        self.append_audit({"action": "report", "status": "queued", "sent": False, "task_id": task_id, "plan": plan})
        return {"ok": True, "sent": False, "status": "queued", "task_id": task_id, **plan}

    def queue_status(self) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute("SELECT status, COUNT(*) FROM report_tasks GROUP BY status").fetchall()
            last = db.execute("SELECT id, status, updated_at, normalized_url, type_code FROM report_tasks ORDER BY updated_at DESC LIMIT 5").fetchall()
        return {
            "ok": True,
            "account": self.username,
            "max_concurrency": self.max_concurrency,
            "min_live_interval_seconds": self.min_live_interval_seconds,
            "counts": {status: count for status, count in rows},
            "recent": [
                {"id": row[0], "status": row[1], "updated_at": row[2], "normalized_url": row[3], "type_code": row[4]}
                for row in last
            ],
        }

    def dry_run(self, payload: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        result = {"ok": True, "sent": False, "status": "dry_run", "dry_run": True, **plan}
        self.append_audit({"action": "report", "status": "dry_run", "sent": False, "plan": plan})
        return result

    def handle_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = build_plan(payload, self.username)
        dry_run = bool(payload.get("dry_run", True))
        confirm = str(payload.get("confirm") or "")
        if dry_run:
            return self.dry_run(payload, plan)
        if confirm != "REPORT":
            result = {"ok": False, "sent": False, "status": "needs_owner_confirm", "dry_run": False, **plan}
            self.append_audit({"action": "report", "status": "needs_owner_confirm", "sent": False, "plan": plan})
            return result
        if not self.live_enabled:
            result = {"ok": False, "sent": False, "status": "failed", "error": "live report disabled; set X_REPORT_LIVE_ENABLED=1", **plan}
            self.append_audit({"action": "report", "status": "live_disabled", "sent": False, "plan": plan})
            return result
        return self.enqueue(payload, plan)

    def start_worker(self) -> None:
        if self._worker_started:
            return
        self._worker_started = True
        try:
            asyncio.get_running_loop().create_task(self.worker_loop())
        except RuntimeError:
            pass

    async def worker_loop(self) -> None:
        while True:
            try:
                await self.process_once()
            except Exception as exc:
                self.append_audit({"action": "report_worker", "status": "failed", "error": str(exc)[:500]})
            await asyncio.sleep(5)

    async def process_once(self) -> None:
        if not self.live_enabled:
            return
        with sqlite3.connect(self.db_path) as db:
            running = db.execute("SELECT COUNT(*) FROM report_tasks WHERE status = 'running'").fetchone()[0]
            if running >= self.max_concurrency:
                return
            recent = db.execute("SELECT MAX(finished_at) FROM report_tasks WHERE status = 'succeeded'").fetchone()[0]
            if recent and int(time.time()) - int(recent) < self.min_live_interval_seconds:
                return
            row = db.execute(
                "SELECT id, payload_json, plan_json, attempts FROM report_tasks WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return
            task_id, payload_json, plan_json, attempts = row
            now = int(time.time())
            db.execute(
                "UPDATE report_tasks SET status = 'running', locked_at = ?, updated_at = ?, attempts = attempts + 1 WHERE id = ?",
                (now, now, task_id),
            )

        payload = json.loads(payload_json)
        plan = json.loads(plan_json)
        try:
            result = await self.execute_plan(payload, plan)
            status = str(result.get("status") or ("succeeded" if result.get("ok") else "failed"))
        except Exception as exc:
            status = "needs_manual" if attempts + 1 >= 3 else "failed"
            result = {"ok": False, "sent": False, "status": status, "error": str(exc)[:1000]}

        now = int(time.time())
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                UPDATE report_tasks
                SET status = ?, updated_at = ?, finished_at = ?, result_json = ?, last_error = ?
                WHERE id = ?
                """,
                (
                    status if status in REPORT_STATUSES else "failed",
                    now,
                    now,
                    json.dumps(result, ensure_ascii=False),
                    str(result.get("error") or "")[:1000],
                    task_id,
                ),
            )
        self.append_audit({"action": "report", "task_id": task_id, "status": status, "sent": bool(result.get("sent")), "result": result, "plan": plan})

    async def execute_plan(self, payload: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        c = self.client_factory()
        screen_name = plan.get("screen_name") or ""
        if not screen_name:
            return {"ok": False, "sent": False, "status": "needs_manual", "error": "missing screen_name; cannot resolve report user without fetching tweet text"}
        target_user = await self.user_id_resolver(c, screen_name)
        user_id = str(target_user)
        action_results = []
        for action in plan["actions"]:
            action_results.append(await self.execute_report_action(plan, action, user_id))
        ok = all(item.get("ok") for item in action_results)
        status = "succeeded" if ok else next((item.get("status") for item in action_results if item.get("status") != "succeeded"), "failed")
        return {"ok": ok, "sent": ok, "status": status, "actions": action_results, "target_user_id": user_id}

    async def execute_report_action(self, plan: dict[str, Any], action: dict[str, Any], user_id: str) -> dict[str, Any]:
        params: dict[str, str] = {
            "client_location": "profile:tweet:caret" if action["action_kind"] == "post" else "profile:user:caret",
            "client_referer": plan["normalized_url"],
            "client_app_id": "3033300",
            "source": action["source"],
            "report_flow_id": str(uuid4()),
            "reported_user_id": user_id,
            "initiated_in_app": "1",
            "lang": "zh-cn",
        }
        if action["action_kind"] == "post":
            params["reported_tweet_id"] = plan["tweet_id"]
            if action.get("force_media_entry"):
                params["is_media"] = "true"

        html_text = self.http_get("https://x.com/i/safety/report_story?" + urllib.parse.urlencode(params))
        parser = parse_report_html(str(html_text))
        step_summaries = [{"title": title_from_html(str(html_text)), "options": sorted(selected_options(parser))[:20]}]
        for option in action["path"]:
            available = selected_options(parser)
            if available and option not in available:
                return {
                    "ok": False,
                    "sent": False,
                    "status": "needs_manual",
                    "error": f"report option not available: {option}",
                    "steps": step_summaries,
                }
            next_params = form_params_from_parser(parser, option)
            html_text = self.http_get("https://x.com/i/safety/report_story?" + urllib.parse.urlencode(next_params))
            parser = parse_report_html(str(html_text))
            missing = required_inputs(parser)
            text = parser.clean_text.lower()
            step_summaries.append(
                {
                    "selected": option,
                    "title": title_from_html(str(html_text)),
                    "required_inputs": missing,
                    "options": sorted(selected_options(parser))[:20],
                }
            )
            if missing:
                return {"ok": False, "sent": False, "status": "needs_details", "required_inputs": missing, "steps": step_summaries}
            if "captcha" in text or "challenge" in text or "cloudflare" in text:
                return {"ok": False, "sent": False, "status": "needs_manual", "error": "challenge page detected", "steps": step_summaries}

        final_text = parser.clean_text
        success = bool(re.search(r"感谢你让我们知道|thanks for letting us know|report_story_complete", final_text, re.I))
        return {
            "ok": success,
            "sent": success,
            "status": "succeeded" if success else "needs_manual",
            "method": "x_report_story_http",
            "action_kind": action["action_kind"],
            "path": action["path"],
            "summary": final_text[:300],
            "steps": step_summaries,
        }
