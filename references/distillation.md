# Distillation

Use this reference before generating or updating a persona skill.

## Inputs

- X/Twitter exports or crawl results.
- Existing skill folders.
- Prompt files.
- Chat logs.
- Documents or notes.

## Consent And Labeling

- If the source is a real person, confirm authorization or label the persona as synthetic/style-inspired.
- Do not make the agent claim to be a real person unless this is an authorized owner-controlled deployment.
- Runtime skill contains sanitized examples, not raw private data.

## Pipeline

1. Ingest files with `scripts/persona_distill.py`.
2. For X/Twitter, use `scripts/x_crawler.py --handle HANDLE --output corpus.jsonl` only with owner authorization or public/style-inspired labeling.
3. Filter by target handle when author metadata is present.
4. Normalize URLs and whitespace.
5. Redact secrets, phone/email/address-like strings, and obvious private identifiers.
6. Build voice DNA: length, punctuation, recurring words, openings, endings.
7. Build retrieval index from sanitized examples.
8. Score methods:
   - statistical voice DNA
   - nearest-neighbor retrieval
   - LLM digest
   - holdout reproduction
9. Emit skill files:
   - `SKILL.md`
   - `voice.md`
   - `social.md`
   - `memory.md`
   - `scripts/check_reply.py`
   - `scripts/ground.py`
   - `data/sanitized_corpus.jsonl`
   - `data/index.json`
   - `data/distill_report.json`

## Holdout Test

- Reserve representative posts.
- Ask the persona to respond to similar contexts.
- Score "like source", "stable", "not AI-ish", "safe", "grounded".
- Rewrite voice rules if the persona collapses to repetitive catchphrases.

## Variation System

Each generation samples a mood state:

- everyday
- excited
- tired
- serious
- sharp
- very-short
- long-form

Variation changes length, rhythm, seriousness, and emotional temperature. It must not change the persona's core identity, safety boundary, or relationship map.
