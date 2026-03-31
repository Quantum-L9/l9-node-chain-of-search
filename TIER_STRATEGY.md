# Perplexity Tier Escalation Strategy

## How the Pipeline Maps to Sonar Models

This microservice implements **cost-optimized tier escalation** — each step in
the chain-of-search pipeline uses the cheapest Perplexity model that delivers
adequate quality for that step's function.

```
┌─────────────────────────────────────────────────────────────────┐
│  PIPELINE STEP        │ SONAR MODEL         │ CONTEXT SIZE     │
├───────────────────────┼─────────────────────┼──────────────────┤
│  1. Decompose Query   │ sonar               │ low              │
│     (generate subs)   │ ($1/1M in, $1/1M out)│ Cheapest tier   │
├───────────────────────┼─────────────────────┼──────────────────┤
│  2. Parallel Search   │ sonar-pro           │ high             │
│     (retrieve + cite) │ ($3/1M in, $15/1M)  │ Max sources      │
├───────────────────────┼─────────────────────┼──────────────────┤
│  3. Evaluate Results  │ sonar               │ medium           │
│     (score relevance) │ ($1/1M in, $1/1M)   │ Balanced         │
├───────────────────────┼─────────────────────┼──────────────────┤
│  4. Gap Analysis      │ sonar               │ medium           │
│     (find holes)      │ ($1/1M in, $1/1M)   │ Balanced         │
├───────────────────────┼─────────────────────┼──────────────────┤
│  5. Synthesize Brief  │ sonar-deep-research │ N/A (built-in)   │
│     (final report)    │ ($2/1M in, $8/1M)   │ 128K context     │
│                       │ +$3/1M reasoning    │ Exhaustive search│
└───────────────────────┴─────────────────────┴──────────────────┘
```

## Why This Strategy?

### Cost Optimization
- Steps 1, 3, 4 are **classification/evaluation tasks** — they don't need
  deep retrieval, so we use `sonar` with `low`/`medium` context ($1/1M)
- Step 2 is the **core retrieval** step — we use `sonar-pro` with `high`
  context to maximize source coverage (2x more results than standard sonar)
- Step 5 is the **synthesis** step — we use `sonar-deep-research` which
  performs its own exhaustive multi-step search internally, combining all
  our pre-gathered findings with additional retrieval

### Quality Optimization
- Sub-query decomposition only needs the LLM's reasoning, not search depth
- Relevance evaluation benefits from moderate context to understand claims
- Gap analysis needs awareness of what's been found, not new search
- Final synthesis benefits maximally from deep research capabilities

## search_context_size Explained

The `search_context_size` parameter (passed via `web_search_options`) controls
how much web content Perplexity retrieves and feeds to the model:

| Size   | Cost    | Use Case                                    |
|--------|---------|---------------------------------------------|
| `low`  | Lowest  | Simple factual queries, high-volume batches  |
| `medium`| Mid    | Moderate complexity, balanced cost/quality   |
| `high` | Highest | Deep research, exploratory, citation-heavy   |

**Important**: `search_context_size` is NOT the same as context window.
- search_context_size = how much web info is retrieved (affects pricing)
- context window = max tokens the model processes (200K for sonar-pro)

## Depth-to-Tier Mapping

| Depth Level | Chains | Search Tier      | Synthesis Tier        | Est. Cost/Query |
|-------------|--------|------------------|-----------------------|-----------------|
| `scan`      | 2      | sonar/medium     | sonar/high            | ~$0.05          |
| `standard`  | 4      | sonar-pro/high   | sonar-pro/high        | ~$0.20          |
| `deep`      | 6      | sonar-pro/high   | sonar-deep-research   | ~$0.80          |
| `exhaustive`| 10     | sonar-pro/high   | sonar-deep-research   | ~$2.00+         |

## Available Sonar Models (March 2026)

| Model                  | Type       | Context | Best For                     |
|------------------------|------------|---------|------------------------------|
| `sonar`                | Search     | 128K    | Fast grounded answers        |
| `sonar-pro`            | Search     | 200K    | Complex multi-step Q&A       |
| `sonar-reasoning`      | Reasoning  | 128K    | Real-time reasoning + search |
| `sonar-reasoning-pro`  | Reasoning  | 200K    | Deep multi-step reasoning    |
| `sonar-deep-research`  | Research   | 128K    | Exhaustive long-form reports |

## API Parameters Reference

### Core Parameters
- `model`: sonar | sonar-pro | sonar-deep-research
- `messages`: [{role, content}] — system + user messages
- `temperature`: 0.0-2.0 (lower = more factual)
- `max_tokens`: max output tokens

### Search Options (web_search_options object)
- `search_context_size`: low | medium | high
- `user_location`: {country, region, city, latitude, longitude}

### Filters
- `search_domain_filter`: ["arxiv.org", "-reddit.com"]
- `search_recency_filter`: day | week | month | year
- `search_after_date_filter` / `search_before_date_filter`: "M/D/YYYY"
- `search_language_filter`: ["en", "fr"]
- `search_mode`: web | academic | sec

### Deep Research Only
- `reasoning_effort`: low | medium | high
