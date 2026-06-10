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
7. Build `data/style_spectrum.json`: corpus-derived feature dimensions, common clusters, rare-but-valid clusters, and safe example anchors.
8. Build retrieval index from sanitized examples.
9. Score methods:
   - statistical voice DNA
   - nearest-neighbor retrieval
   - LLM digest
   - holdout reproduction
10. Emit skill files:
   - `SKILL.md`
   - `voice.md`
   - `social.md`
   - `crisis_support.md`
   - `memory.md`
   - `scripts/check_reply.py`
   - `scripts/ground.py`
   - `data/sanitized_corpus.jsonl`
   - `data/index.json`
   - `data/style_spectrum.json`
   - `data/distill_report.json`

## Holdout Test

- Reserve representative posts.
- Ask the persona to respond to similar contexts.
- Score "like source", "stable", "not AI-ish", "safe", "grounded".
- Rewrite voice rules if the persona collapses to repetitive catchphrases.

## Style Spectrum

Do not reduce a persona to fixed presets such as "long", "cold", "soft", or "sharp". Each generation should sample a `style_sample` from `data/style_spectrum.json` and ground the draft against nearby source examples.

The spectrum should include:

- Length bucket and line shape.
- Intent, such as specific question, small opinion, complaint/pushback, self-reaction, timeline reaction, or observation.
- Stance, texture density, punctuation shape, opening shape, and ending shape.
- Topic family and 1-3 safe example anchors.
- Rare-but-valid clusters so low-frequency real expressions survive instead of being forced back to the median style.

Variation changes concrete topic, length, rhythm, stance, punctuation, and texture. It must not change the persona's core identity, safety boundary, or relationship map.

## Crisis Voice Test

Distilled personas need a separate crisis-support voice, because generic safety templates make the bot sound fake.

- Add `crisis_support.md` to the emitted skill.
- Treat "want to die", "不想活", "想死", goodbye notes, and hopelessness as crisis-support contexts, not ordinary blocked topics.
- The reply should stay in persona voice, acknowledge the feeling, give one tiny next step, and avoid AI disclaimers or resource-list formatting.
- High-immediacy danger may mention nearby people, local emergency services, or a crisis line, but still in natural language.
