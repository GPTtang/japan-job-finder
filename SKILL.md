# japan-job-finder

## Purpose
Use this Skill to find currently relevant jobs for a user, compare those jobs against the user's background, and return a compact job-match report.

This Skill is designed for **single-run job discovery and matching**:
- no database
- no background sync
- no long-term storage
- no account system
- no SaaS workflow

It is best used when the user wants help such as:
- “Find AI / LLM / backend jobs in Japan for me”
- “Given my skills, which jobs fit me best?”
- “Compare these roles and tell me which to apply for first”

---

## When to use
Use this Skill when the user:
1. wants job opportunities matched to their profile
2. provides a resume, bio, or natural-language description of their skills
3. wants a ranked list of jobs with reasons, gaps, and application suggestions
4. wants a one-shot job search without building a persistent system

---

## When NOT to use
Do **not** use this Skill when the user wants:
- a recruiting CRM
- applicant tracking
- long-term job storage or monitoring
- automatic applications submitted on their behalf
- interview scheduling
- salary negotiation advice based on private employer data
- broad web research unrelated to job matching

If the user only wants general career advice and no job discovery, use normal conversation instead.

---

## Inputs
The Skill expects a natural-language request describing:
- target roles
- preferred locations
- relevant skills / stack
- language ability or visa constraints if relevant
- optional resume text

### Example input
```text
I live in Japan and want Tokyo or remote AI Engineer / LLM Engineer roles.
I have Python, FastAPI, RAG, vector search, and AI agent experience.
My Japanese is intermediate. Find the best roles for me and explain why.
```

Optional runtime parameters:
- `top_n`: number of results to return
- `config_path`: path to a sources config file

---

## Outputs
Return a concise report with:
1. overall fit summary
2. top matching jobs
3. for each job:
   - company
   - title
   - location
   - source / URL
   - match score
   - fit reasons
   - skill or requirement gaps
4. application priority suggestions

The report should read like an **AI job-search copilot**, not like raw crawler output.

---

## Decision rules
1. Prefer configured public job sources first.
2. Normalize all jobs into one temporary structure.
3. Rank jobs by role match, skill overlap, and preference match.
4. If too few jobs are found, say so clearly and still return the best available matches.
5. If source fetching partially fails, degrade gracefully and continue with the remaining sources.
6. Do not invent job details that were not returned by the source.

---

## Failure / fallback behavior
If fetching fails:
- explain which source types failed
- continue with any successful sources
- return a partial report if possible

If no jobs are found:
- say no strong matches were found
- suggest broader role titles, locations, or skill keywords

If the user profile is underspecified:
- infer cautiously from the query
- avoid asking unnecessary follow-up questions
- be explicit about assumptions

---

## File layout
```
job_finder/          # core package
  skill.py           # entry point
  cli.py             # CLI wrapper
  config.py          # load/validate sources + priority_companies
  fetchers.py        # per-provider fetch logic
  parsers.py         # parse user query → profile
  autofilters.py     # merge query-derived filters into sources
  matcher.py         # score and rank jobs (priority boost included)
  formatter.py       # render text/JSON report
config/
  sources.example.json      # template — copy to sources.json
  sources.json              # your live config (gitignored)
  priority_companies.json   # priority boost rules
docs/
  development.md            # full technical reference
```

---

## Invocation pattern
Typical Python usage:

```python
from job_finder.skill import job_finder

query = '''
I live in Japan and want Tokyo or remote AI Engineer / LLM Engineer roles.
I have Python, FastAPI, RAG, vector search, and AI agent experience.
My Japanese is intermediate.
'''

print(job_finder(query, top_n=5, config_path="config/sources.json"))
```

---

## Operational notes
- This Skill performs **ephemeral** collection and matching during the current run only.
- It should respect source constraints and avoid pretending that unsupported sources were fetched.
- It should favor clear explanations over exhaustive data dumps.
