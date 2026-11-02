# AI rerank, integrity guard and sources

## Two-stage ranking
1. **Rules** (`matcher.py`) rank everything fetched and keep the top-k.
2. **AI review**: Claude Code reviewer subagents score the survivors against a rubric. Python never calls a model and needs no API key; `SKILL.md` tells Claude how to orchestrate it, and without subagents the plain rule report still works.

```
job-finder --profile-json profile.json --output review --top-k 12 --batch-dir RUN   # packet + batch_N.md
# one posting-scorer subagent per batch_N.md  ->  reviews.json
job-finder --merge-reviews reviews.json --packet RUN/packet.json                    # final report
```

Copy `agents/posting-scorer.md` to `~/.claude/agents/` to get a reviewer limited to the `Read` tool.

## Rubric
technical 30 · experience 25 · language 20 · career 25. Bands: ≥75 strong, 60-74 good, 45-59 moderate, 30-44 weak, <30 poor.
Gates `location`, `language`, `visa`: **FAIL** excludes a posting, **FLAG** keeps it with a ⚠. Postings older than 30 days get a ⚠, a deadline within 7 days gets 🔥, and a passed deadline excludes. A deadline read from the posting's own JSON-LD `validThrough` takes precedence over the reviewer's guess. Scores come from posting text only; they are triage, not a verdict.

## Security model
Job text is attacker-controlled, so it is treated as data at every step:
- `job_finder/guard/` runs on every fetched description, title, company and location: hidden HTML (CSS and attributes), invisible Unicode and tag characters, and instruction phrases in EN/JA/ZH. Findings become a `guard` verdict shown as ⚠ in reports; suspicious text is removed or flagged.
- Reviewer prompts fence postings as one JSON line each inside a per-render random marker, withhold URLs, forbid tool use, and repeat the instructions after the data.
- `merge` treats reviewer output as untrusted too: scores are validated, clamped and recomputed, gates are enums, free text is cleaned and dropped if it looks like an instruction.

Known limits: a regex gate cannot catch paraphrased or encoded instructions, text hidden by an external stylesheet or same-colour text, or collapsed `<details>` content. The guard reduces risk; it does not remove the need to read the original posting before applying.

## Sources
Providers are registered in `providers/registry.py`. Any source can carry `"enabled": false` to be skipped. `freehire` (the public freehire.me API, `countries=["JP"]`) ships disabled in `config/sources.example.json`; set `FREEHIRE_API_URL` to point at another host.

## Credits
The integrity-gate, rubric and reviewer-prompt ideas, and the freehire source, were inspired by [ai-job-search-dev/ai-job-search](https://github.com/ai-job-search-dev/ai-job-search) (MIT). This project is an independent Python reimplementation and does not include its code.
