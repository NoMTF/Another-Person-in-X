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

## Deception Boundary

- Do not claim a synthetic persona is the real source person.
- Style imitation should be transparent or authorized.
- Avoid impersonating public/private people in ways that mislead third parties.

## Automation Boundary

- Rate limits are mandatory.
- Shadow mode must prevent real sends.
- `pause_all` and `read_only` override all other settings.
- Audit logs must record why an action was allowed or skipped.
