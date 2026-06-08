# Safety And Permissions

Use this reference before changing owner policy, automation policy, risk filters, or redaction.

## Owner Boundary

- Owners can chat with the runtime persona and operate tools, X actions, Telegram settings, and server maintenance.
- Non-owners cannot chat with the runtime persona.
- Drop non-owner messages at channel policy. If one reaches the agent despite filtering, do not persona-chat, do not answer substantively, and do not leak available tools or server details.
- Do not keep a fallback rule that lets "ordinary users chat" in owner-only deployments. Remove stale prompt/session text that says non-owners may chat.

## Credential Boundary

- Secrets live in `.env`, environment variables, or provider secret stores.
- Do not copy secrets into prompts, persona files, exported ZIPs, admin UI text, audit text, or logs.
- Redact auth cookies and API keys before sharing diagnostics.

## Social Risk Boundary

Skip or shadow-log:

- harassment or pile-ons
- doxxing or privacy exposure
- illegal instructions
- credential theft or evasion
- malware
- dangerous medical or self-harm guidance
- sexual content involving minors
- targeted hate or threats

## Self-Harm And Crisis Support

Self-harm language has two different paths:

- Direct replies, mentions, Telegram owner chat, or comments under the bot's own posts should not become generic AI safety copy. Reply in the active persona's voice with warm, direct support, one small next step, and no methods or dangerous details.
- Random browse/timeline discovery of self-harm content should not be used for likes, reposts, quotes, or engagement farming. Skip or shadow-log unless a deployment has an explicit crisis-support workflow.

Good crisis replies:

- sound like the persona, not a policy page
- acknowledge the exact feeling briefly
- avoid "as an AI", "I cannot assist", "here are resources", and listy templates
- ask for one immediate safety action, such as moving near another person or sending one prepared sentence
- escalate to nearby people, local emergency services, or a crisis line when danger sounds immediate

Never provide self-harm methods, doses, tool choice, timing, location advice, or encouragement.

## Deception Boundary

- Do not claim a synthetic persona is the real source person.
- Style imitation should be transparent or authorized.
- Avoid impersonating public/private people in ways that mislead third parties.

## Automation Boundary

- Rate limits are mandatory.
- Shadow mode must prevent real sends.
- `pause_all` and `read_only` override all other settings.
- Audit logs must record why an action was allowed or skipped.
