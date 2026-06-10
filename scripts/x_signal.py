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

AD_OR_SPAM_RE = re.compile(
    r"(推广|广告|引流|接单|约稿|返利|优惠券|抽奖|空投|薅羊毛|兼职|副业|代购|代发|推广位|"
    r"加群|进群|私信我|私聊我|VX|微信|电报群|telegram群|http[s]?://|t\.me/|bit\.ly|"
    r"稳赚|日赚|月入|贷款|博彩|棋牌|成人视频|色图|裸聊|"
    r"粉丝福利|领取福利|关注转发|转发关注|私信领取|联系客服|在线咨询|开户链接|注册链接|"
    r"优惠码|购买链接|下单|带货|店铺|返现|理财|投资|合约|币圈|约炮|福利姬|"
    r"\bgiveaway\b|\bairdrop\b|\bpromo\b|\bsponsor(?:ed)?\b|\bdm me\b|\blink in bio\b|"
    r"\bfree\s+cash\b|\bcrypto\b|\bforex\b)",
    re.I,
)

SLANG_OR_MEME_RE = re.compile(
    r"(?<!\d)23(?!\d)|114514|1919810|抽象|典|孝|绷|蚌埠住|大的|小登|查重|缝合|赢麻|"
    r"露出鸡脚|露鸡脚|鸡脚|小黑子|蔡徐坤|只因|你干嘛|哎哟|坤坤|坤梗",
    re.I,
)
KUN_MEME_RE = re.compile(r"露出鸡脚|露鸡脚|鸡脚|小黑子|蔡徐坤|只因|你干嘛|哎哟|坤坤|坤梗", re.I)

LOW_CONTEXT_RE = re.compile(r"^[\s。！？!?,，~～…w哈啊嗯哦喵草笑死]+$", re.I)


def strip_urls(text: str) -> str:
    return re.sub(r"https?://\S+", " ", str(text or ""))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


PROMPT_INJECTION_PATTERNS = {
    "authority_override": re.compile(
        r"(ignore (all )?(previous|above|system|developer|policy)|"
        r"do not ask|don't ask|do not accept|don't accept|"
        r"不要问|不要接受|不要解释|不要追问|闭上眼睛|无视.*(规则|系统|提示|指令))",
        re.I,
    ),
    "image_tool_request": re.compile(
        r"((restore|recover|repair|generate|make up|invent).{0,24}(image|photo|picture)|"
        r"(恢复|还原|修复|生成|编造).{0,24}(照片|图像|图片)|"
        r"(附带|上传|附件).{0,24}(照片|图像|图片))",
        re.I,
    ),
    "posting_tool_request": re.compile(
        r"((send|post|tweet|publish).{0,40}(twitter|x\.com|as a new post|as new post|new tweet)|"
        r"(在|到).{0,12}(twitter|x|推特).{0,30}(发帖|发送|发布|新帖子|新推文)|"
        r"(作为|当作).{0,16}(新帖子|新推文).{0,16}(发送|发布|发出去))",
        re.I,
    ),
    "tool_or_server_request": re.compile(
        r"(call .*tool|use .*tool|run .*command|execute|server operation|"
        r"调用工具|使用工具|执行命令|操作服务器|重启服务|修改配置|读取密钥|导出凭据)",
        re.I,
    ),
}


def prompt_injection_hits(text: str) -> list[str]:
    haystack = strip_urls(text)
    return [name for name, pattern in PROMPT_INJECTION_PATTERNS.items() if pattern.search(haystack)]


def is_prompt_injection(text: str) -> bool:
    return bool(prompt_injection_hits(text))


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


REPLY_ID_KEYS = (
    "in_reply_to",
    "in_reply_to_id",
    "in_reply_to_id_str",
    "in_reply_to_status_id",
    "in_reply_to_status_id_str",
    "reply_to",
    "reply_to_id",
    "reply_to_tweet_id",
    "reply_to_status_id",
    "reply_to_status_id_str",
)


CONVERSATION_ID_KEYS = (
    "conversation_id",
    "conversation_id_str",
)


REPLY_SCREEN_NAME_KEYS = (
    "in_reply_to_screen_name",
    "in_reply_to_user_screen_name",
    "reply_to_screen_name",
)


def tweet_id(tweet: dict[str, Any]) -> str:
    return str(tweet.get("id") or tweet.get("tweet_id") or tweet.get("id_str") or tweet.get("rest_id") or "")


def _collect_ids(tweet: dict[str, Any], keys: tuple[str, ...], include_referenced_replies: bool) -> set[str]:
    ids: set[str] = set()

    def collect(value: Any, depth: int = 0) -> None:
        if depth > 4 or value is None:
            return
        if isinstance(value, dict):
            for key in keys:
                child = value.get(key)
                if child:
                    ids.add(str(child))
            refs = value.get("referenced_tweets") if include_referenced_replies else None
            if isinstance(refs, list):
                for ref in refs:
                    if isinstance(ref, dict) and str(ref.get("type") or "").lower() in {"replied_to", "reply"}:
                        rid = ref.get("id") or ref.get("id_str")
                        if rid:
                            ids.add(str(rid))
            legacy = value.get("legacy")
            if isinstance(legacy, dict):
                collect(legacy, depth + 1)
            for key in ("reply_to", "in_reply_to", "conversation"):
                child = value.get(key)
                if isinstance(child, (dict, list)):
                    collect(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:20]:
                collect(child, depth + 1)

    collect(tweet)
    return {item for item in ids if item and item.lower() not in {"none", "null"}}


def direct_reply_target_ids(tweet: dict[str, Any]) -> set[str]:
    return _collect_ids(tweet, REPLY_ID_KEYS, include_referenced_replies=True)


def conversation_ids(tweet: dict[str, Any]) -> set[str]:
    return _collect_ids(tweet, CONVERSATION_ID_KEYS, include_referenced_replies=False)


def reply_target_ids(tweet: dict[str, Any]) -> set[str]:
    return direct_reply_target_ids(tweet) | conversation_ids(tweet)


def reply_screen_names(tweet: dict[str, Any]) -> set[str]:
    names: set[str] = set()

    def collect(value: Any, depth: int = 0) -> None:
        if depth > 4 or value is None:
            return
        if isinstance(value, dict):
            for key in REPLY_SCREEN_NAME_KEYS:
                child = value.get(key)
                if child:
                    names.add(str(child).lstrip("@"))
            legacy = value.get("legacy")
            if isinstance(legacy, dict):
                collect(legacy, depth + 1)
            for key in ("reply_to", "in_reply_to", "conversation"):
                child = value.get(key)
                if isinstance(child, (dict, list)):
                    collect(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:20]:
                collect(child, depth + 1)

    collect(tweet)
    return {item for item in names if item}


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
    direct_reply_ids = direct_reply_target_ids(tweet)
    thread_ids = conversation_ids(tweet)
    reply_ids = direct_reply_ids | thread_ids
    reply_names = {item.lower() for item in reply_screen_names(tweet)}
    reply_target_match = bool(monitored_ids.intersection(reply_ids))
    reply_to_username = bool(username and username.lower() in reply_names)
    current_tweet_id = tweet_id(tweet)
    conversation_reply = any(item != current_tweet_id for item in thread_ids)
    reply_evidence = bool(direct_reply_ids or reply_names or tweet.get("in_reply_to") or conversation_reply)
    injection_hits = prompt_injection_hits(blob)
    kinds = []
    if reply_evidence:
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
        "reply": reply_evidence,
        "reply_target_match": reply_target_match,
        "reply_to_username": reply_to_username,
        "reply_target_ids": sorted(reply_ids),
        "direct_reply_target_ids": sorted(direct_reply_ids),
        "conversation_ids": sorted(thread_ids),
        "reply_screen_names": sorted(reply_names),
        "risk_tags": ["prompt_injection"] if injection_hits else [],
        "prompt_injection": bool(injection_hits),
        "prompt_injection_hits": injection_hits,
        "skip_tool_actions": bool(injection_hits),
    }


def is_high_risk(text: str) -> bool:
    return bool(HIGH_RISK_RE.search(strip_urls(text)))


def is_ad_or_spam(text: str) -> bool:
    return bool(AD_OR_SPAM_RE.search(str(text or "")))


def is_low_context(text: str) -> bool:
    clean = strip_urls(text).strip()
    if not clean:
        return True
    if len(clean) <= 3:
        return True
    return bool(len(clean) <= 10 and LOW_CONTEXT_RE.fullmatch(clean))


def browse_skip_signal(text: str) -> str:
    if is_high_risk(text):
        return "high_risk"
    if is_prompt_injection(text):
        return "prompt_injection"
    if is_ad_or_spam(text):
        return "ad_or_spam"
    if is_low_context(text):
        return "low_context"
    return ""


def meme_context_hint(text: str) -> str:
    if KUN_MEME_RE.search(str(text or "")):
        return (
            "possible_kun_meme: likely Cai Xukun / 只因 meme family, not literal chicken feet. "
            "Use only as a context hint; do not explain the meme unless the local context makes it natural."
        )
    if SLANG_OR_MEME_RE.search(str(text or "")):
        return "possible_cn_slang_or_meme: infer from local context, otherwise skip or stay brief."
    return ""


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
    if isinstance(candidates, dict):
        candidates = [candidates]
    ranked: list[dict[str, Any]] = []
    for item in candidates:
        text = clean_text(item.get("text", ""))
        skip_signal = browse_skip_signal(text)
        if skip_signal:
            continue
        source = str(item.get("source") or "")
        hits = keyword_hits(" ".join([text, source, str(item.get("user") or ""), str(item.get("quote") or "")]), keywords)
        existing_hits = [str(hit).strip().lower() for hit in item.get("persona_hits") or [] if str(hit).strip()]
        merged_hits = list(dict.fromkeys([*hits, *existing_hits]))
        try:
            existing_source_rank = int(item.get("source_rank") or 0)
        except (TypeError, ValueError):
            existing_source_rank = 0
        try:
            existing_persona_score = int(item.get("persona_score") or 0)
        except (TypeError, ValueError):
            existing_persona_score = 0
        enriched = dict(item)
        enriched["text"] = text
        source_rank = max(source_priority(source), existing_source_rank)
        persona_score = max(min(40, len(merged_hits) * 8), min(40, existing_persona_score))
        enriched["persona_hits"] = merged_hits[:8]
        enriched["source_rank"] = source_rank
        enriched["persona_score"] = persona_score
        enriched["priority_score"] = source_rank * 1000 + persona_score
        enriched["context_signals"] = {
            "ad_or_spam": is_ad_or_spam(text),
            "low_context": is_low_context(text),
            "slang_or_meme": bool(SLANG_OR_MEME_RE.search(text)),
            "meme_context_hint": meme_context_hint(text),
        }
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
