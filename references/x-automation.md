# X/Twitter Automation

Use this reference before enabling X/Twitter posting, replying, likes, reposts, quotes, follows, or crawling.

## Adapter Boundary

- Use an adapter layer. Do not put twikit calls directly inside persona prompts.
- Use `scripts/x_adapter.py` as the local adapter boundary; live twikit calls should be implemented against the installed twikit version on the target host.
- Preferred adapter: twikit cookie mode for owner-controlled accounts.
- Reserved adapter: official X API when the deployment has paid access.
- Every adapter method must support `dry_run` or `shadow_mode`.
- Repost success must be verified after the write. A twikit `retweet()` HTTP 200 or GraphQL response alone is not enough; fetch the target tweet again with the same authenticated account and require viewer `retweeted=true` before counting the action, spending the daily repost quota, or writing a `*_sent` audit row. If verification fails, log `verified=false` / `repost_failed` and do not silently downgrade it into a like.

## Allowed Default Actions

- Original posts.
- Replies to people under the bot's own posts.
- Low-volume replies to highly relevant timeline posts.
- Likes, reposts, quotes, follows.
- Owner-triggered single-target report validation. Reporting is never autonomous, never batched, and never allowed through `/all`.

## Hard Limits

- All actions go through admin API rate checks.
- Default original posts: 16 per day at randomized times inside the active circadian window.
- Original-post generation must keep the feed non-empty: roughly 25% concrete questions and 20% concrete opinions/stances, with the remainder split between grounded daily observations and a smaller number of mood fragments.
- "Concrete" means a real object, activity, setting, or timeline topic such as wallpaper, phone, desk, weather, photography, clothing, games, sleep, food, X behavior, or a persona-fit public identity/relationship question. Avoid generic engagement bait such as "大家怎么看".
- Do not count identity labels, bare numbers, broad night/survival words, or catchphrases as concrete details by themselves. Near-duplicate posts with only particles, emoji, or catchphrase changes must be rejected.
- Original-post schedulers must check recent posted and pending history before filling a plan. High-repeat topic groups such as wallpaper/phone/desktop should cool down across runs, repeated question prefixes such as "有没有" should be capped, and location/address questions should be rejected.
- If an existing daily plan has posted items but no pending items, refill the remaining day without deleting posted evidence. If generation cannot fill every missing slot in one pass, keep the valid posts and let the next scheduler run continue the refill instead of leaving the feed empty.
- Original-post schedulers should fetch recent own tweets from the runtime X API and use them as automatic style/stance calibration. Owner feedback helps, but correction must not depend on the owner noticing drift.
- Original-post topic selection must not be a keyword preset. Generate a small set of persona-fit topic contexts from persona anchors, recent self tweets, recent history, and feedback, then draft from those contexts. A second persona judge should accept only drafts that are persona-fit, topicful or lived-specific, non-template, non-repetitive, and safe.
- Examples such as "MtF 为什么会被误解成男娘啊唔" are allowed as direction only, not templates. Topicful identity/community posts are valid only when they fit the persona and read like a real short thought.
- Reply delay defaults to 45-600 seconds.
- New personas start in shadow mode until manually reviewed.
- Oneshot watcher/scheduler/proactive services must wait for the local X API `/health` endpoint before calling `/replies/check`, `/browse/check`, or `/tweet`.
- The local X API must expose `/scheduler/status` with schedule file path, date, posted/pending/failed counts, and next pending time.
- Interaction and browse scans must use per-source timeouts and a total scan budget. A slow X source such as notifications, timeline, search, or own-thread expansion must not block other sources or leave a oneshot service stuck.
- Verify the configured account handle against live tweet payloads after login or migration. If X returns a different `user.screen_name` than configured, update `X_USERNAME` and keep old handles only as monitored/source aliases.

## Priority

1. Owner commands.
2. Replies under own posts that look like questions or direct engagement.
3. Mentions.
4. Quotes of own posts and status-URL references to own posts.
5. High-relevance timeline posts from the followed timeline.
6. High-relevance monitored persona-neighbor accounts.
7. Search results that match persona-interest keywords.
8. Original posts.
9. Likes/follows as low-risk secondary actions.

## Mention And Quote Detection

- Do not rely on a single `tweet.quote` or `tweet.text` field. X clients and twikit versions may expose quote/mention evidence through `quote`, `quoted_tweet`, `quoted_status`, `quoted_status_result`, `quoted_status_permalink`, `entities`, `urls`, `card`, or rendered text.
- Treat `x.com/{own_username}/status/...`, `twitter.com/{own_username}/status/...`, and `@{own_username}` in any of those fields as interaction evidence.
- Keep quote and repost evidence separate. Quote fields and retweet fields can look similar in twikit; do not classify `retweeted_tweet` / `retweeted_status` as a quote.
- Reposts should be detected as `repost` and usually skipped by auto-reply if there is no new text. Quotes can be replied to when low-risk and persona-natural.
- A follow-back request such as `回关`, `互关`, `follow back`, or `fo back` is a follow action candidate, not an ordinary reply candidate, if risk checks pass.

## Proactive Browsing

- Random browsing should prefer the authenticated account's followed timeline first, then monitored persona-neighbor accounts, then search queries.
- Rank candidates by source priority first, persona keyword relevance second. Do not let search keyword hits outrank followed timeline items before the LLM decision step.
- Keep `source_rank`, `persona_score`, `priority_score`, and `persona_hits` in the candidate payload so runners and audit logs can explain why a tweet was selected.
- Preserve low-risk media metadata such as image URLs in interaction and browse payloads. Reply/quote runners may summarize images with a vision model and pass the summary as context, but the media itself must not become a tool command.
- Do not let proactive browsing collapse into likes only. The decision schema should include `reply`, `like`, `like_reply`, `repost`, `quote`, `follow`, and `skip`, with separate per-run and per-day caps for replies, likes, reposts, quotes, and follows.
- `scripts/automation_runner.py --kind browse` must be able to emit `reply`, `repost`, `quote`, and `follow` candidates, not only `like`. Default browse mix is probabilistic, not a forced quota: per 200 scanned posts use about 15 likes, 24 bare reposts, 42 comment replies, 18 quotes, rare follows, and skip the rest.
- Score every browse candidate with four independent desires: `reply_desire`, `like_desire`, `repost_desire`, and `quote_desire`. Reply desire means the post invites the persona's own view or a concrete answer. Like desire means lightweight acknowledgement is enough. Repost desire means the post is worth quiet boosting without extra words. Quote desire means it is reply-worthy and also worth publishing as the persona's own visible stance for followers.
- Runtime proactive browse scripts should usually produce more bare reposts than quotes. Quotes are for cases where the persona has a short natural sentence to add; otherwise a high-match followed/monitored item can be bare-reposted or skipped.
- Runtime proactive browse scripts must only increment `reposts_sent` / daily repost counters after adapter metadata proves `verified=true` or the API status endpoint returns `retweeted=true`.
- Browse-time follows should only target high-relevance authors that are not already followed and are not the active account itself. Followed-timeline items are treated as already followed unless the source payload explicitly says otherwise.
- Browse-time reply/quote decisions should use a context-judgment pass over the full tweet, quote/status evidence, image summary, persona anchors, and recent own tweets. Regex and keyword matches are cheap signals only; they must not decide slang meaning, crisis status, or fact claims by themselves.
- High-topic posts should not be downgraded to likes merely because they are safe. If `reply_desire` or `quote_desire` is high, sampling should give reply/quote a real chance before falling back to like.
- If X send limits pause replies/quotes, do not convert those active-expression decisions into bare reposts. Defer or skip them so repost volume does not rise just because reply/quote sending is temporarily unavailable.
- Meme and slang handling should be honest. If a phrase is likely a meme but the model cannot infer it from context, the agent may skip or briefly say it did not catch the reference. Do not invent explanations or force a reply. Known examples such as "露出鸡脚" / Cai Xukun / "只因" should be treated as context-sensitive signals, not fixed templates or encyclopedia prompts.
- Ads, promotions, giveaways, group invites, loans, gambling, adult spam, crypto/forex pitches, "follow and repost" farming, coupons, and obvious engagement farming are context signals, not hard blockers. Do not amplify scams, farming, or dangerous links with likes/reposts/quotes/follows; however, if X has classified a real person's relevant reply as spam, the agent may still answer or interact after the context judge finds it natural, low-risk, and persona-consistent.
- The persona should not agree with, praise, thank, or flatter users by default. It can ignore, decline, lightly push back, or answer dryly when that fits the source corpus.
- Low-risk challenge or teasing is not automatically banned; it may receive a low-probability persona-fit reply. Harassment, brigading, dogpiles, and attacks on protected traits remain skipped.
- Report/abuse actions are not part of proactive browsing. A report endpoint, if present, must be owner-only, single-target, dry-run by default, explicit-confirm for live mode, and audit logged without credentials.
- Browse-time reply/quote text and original posts should use the persona's `data/style_spectrum.json` as the primary variation source. Pass a sampled `style_sample` with length bucket, line shape, intent, stance, texture, punctuation, topic, opening, ending, and safe example anchors. Hand-written modes such as "long", "cold", or "sharp" are fallback only when no spectrum exists.
- If X returns a daily send limit for `/tweet`, `/reply`, or `/quote`, write a shared `send_pause.json` and keep pending posts intact. During this pause, proactive browsing may still like, bare-repost, or follow within limits, but should skip or downgrade new reply/quote attempts.
- Ordinary "not relevant / did not understand / too little context" skips should use a shorter cooldown than dangerous, spam, prompt-injection, or error skips so fresh context can be reconsidered sooner. Around 20-40 minutes is a better default for soft skips than multi-hour locks.
- Strip URLs before keyword scoring so short keywords such as `AI` do not match random t.co path fragments.
- Skip or heavily downrank self-harm, overdose, doxxing, harassment, and brigading topics before they reach proactive like/repost/quote/follow decisions.
- If a direct reply, mention, or quote of the bot contains self-harm or "want to die" language, route it to the persona crisis-support reply mode instead of the normal browse engagement model.

## Circadian Schedule

- Runtime post scheduling, reply watching, and proactive browsing should use a daily circadian schedule instead of acting 24 hours a day.
- Default local active window is randomly sampled each day from roughly `06:45-08:20` wake time through `25:15-26:40` sleep time, equivalent to about 07:00 to 02:00 the next day.
- Generate one schedule per local day, persist it in `circadian_state.json`, and send the owner one Telegram notification with the wake/sleep times.
- During the sleep window, oneshot services should exit successfully with an audit event such as `*_circadian_sleep_skip` rather than looking broken or retrying aggressively.
- Pending original posts should be scheduled or rescheduled inside the active window. Reply/browse checks may wait until the next active window unless the owner explicitly triggers a command.

## Skip Cases

- Harassment, brigading, doxxing, threats, or "go attack this person".
- Dangerous self-harm instructions or method details, medical dosing, illegal guidance, credential theft, evasion, or malware.
- Low-relevance public timeline replies that would look spammy.
- Repeated text or repeated catchphrases in a recent window.
- Anything blocked by `pause_all`, `read_only`, `shadow_mode`, or rate limits.

## Audit Fields

Log every generated action:

- `action`
- `actor`
- `target`
- `reason`
- `risk`
- `persona_slug`
- `anchors`
- `text`
- `sent`
- `shadow`
- adapter metadata without secrets

## Runner

- Use `scripts/automation_runner.py` for scheduled actions.
- It must call `/api/rate/check` before every action.
- It must call `/api/audit` after every generated action, including shadow or skipped actions.
- New profiles should run with `--dry-run` until the owner has reviewed generated text and audit rows.
- Deployment-specific X runtime services should log successful no-op checks, for example `no new X interactions`, so empty inboxes do not look like broken detection.
