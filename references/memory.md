# Memory

Use this reference before changing long-term memory or context injection.

## Three-Layer Design

1. Official OpenClaw memory layer: use `MEMORY.md`, daily notes, and any available memory-core or memory-wiki mechanisms in the installed OpenClaw runtime.
2. Factory local layer: SQLite tables and FTS5 search in `factory.sqlite3`.
3. Persona digest layer: inject compact high-signal digests into prompts instead of full history.

## What To Store

- Stable preferences.
- Relationships and owner corrections.
- Commitments and open loops.
- Persona calibration failures.
- Posts/replies that performed unusually well or badly.
- Safety refusals or risky near-misses.

## What Not To Store

- Raw credentials, cookies, API keys, or tokens.
- Addresses, IDs, phone numbers, private medical details, or precise age/location details.
- Low-value chat filler.
- Full raw X corpus in runtime memory.

## Write Format

Every memory needs:

- category
- content
- source
- confidence
- persona slug
- timestamp
- optional metadata

## Context Injection

- Retrieve only relevant rows.
- Summarize multiple rows into a digest.
- Keep memory snippets short and source-aware.
- Prefer "the user prefers..." over quoting raw private text.
- Use `POST /api/memory/digest` to build persona-scoped context snippets for runtime injection. This returns a bounded digest and never the whole memory table.
