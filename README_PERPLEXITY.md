# 🔍 Chain-of-Search — Perplexity Edition

A Perplexity-native chain-of-search microservice that layers across Sonar's
model tiers (sonar → sonar-pro → sonar-deep-research) with automatic
`search_context_size` escalation at each pipeline stage.

## Architecture: Tier Escalation

```
User Query
    │
    ▼
┌──────────────────────────────────┐
│ 1. DECOMPOSE (sonar / low)      │  Cheap sub-query generation
│    Query → 3-6 sub-queries      │  ~$0.001 per call
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ 2. SEARCH (sonar-pro / high)    │  Deep parallel retrieval
│    Sub-queries → Rich results   │  2x sources, full context
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ 3. EVALUATE (sonar / medium)    │  Relevance scoring + claims
│    Results → Scored claims      │  Balanced cost/quality
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ 4. GAP ANALYSIS (sonar / medium)│  Coverage assessment
│    Claims → Gaps → Follow-ups   │
└──────────────┬───────────────────┘
          ┌────┴────┐
          │ Gaps?   │──Yes──→ Back to Step 2
          └────┬────┘
               │ No
               ▼
┌──────────────────────────────────┐
│ 5. SYNTHESIZE                   │  Full deep research report
│    (sonar-deep-research / high) │  128K context, reasoning
│    All claims → Research brief  │  Hundreds of sources
└──────────────────────────────────┘
```

## Quick Start

### 1. Set your API key
```bash
cp .env.perplexity .env.perplexity.local
# Edit with your key: PERPLEXITY_API_KEY=pplx-xxxxx
```

### 2. Run with Docker
```bash
docker compose -f docker-compose.perplexity.yml up --build
```

### 3. Or run locally
```bash
pip install -r requirements.perplexity.txt
export PERPLEXITY_API_KEY=pplx-xxxxx
python main_perplexity.py
```

## API Usage

### Basic research
```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the most effective RAG architectures in 2025?",
    "depth": "deep",
    "max_chains": 6,
    "output_format": "markdown"
  }'
```

### With domain filtering
```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Latest advances in retrieval-augmented generation",
    "depth": "exhaustive",
    "domain_filter": ["arxiv.org", "github.com", "huggingface.co"],
    "recency_filter": "month",
    "search_mode": "academic"
  }'
```

### Stream progress (SSE)
```bash
curl -N http://localhost:8000/research/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "Compare CoRAG vs single-pass RAG", "depth": "standard"}'
```

### View available tiers
```bash
curl http://localhost:8000/tiers
```

## Files

| File | Purpose |
|------|---------|
| `perplexity_client.py` | Sonar API client with tier routing |
| `chain_of_search_perplexity.py` | Core engine with tier escalation |
| `main_perplexity.py` | FastAPI endpoints |
| `TIER_STRATEGY.md` | Full explanation of tier/cost strategy |
| `.env.perplexity` | API key configuration |
| `Dockerfile.perplexity` | Container build |
| `docker-compose.perplexity.yml` | Docker Compose config |
| `requirements.perplexity.txt` | Python dependencies |

## Using Both Backends

This is a **supplemental** module for the base chain-of-search microservice.
You can run either backend:

```bash
# Generic backend (any OpenAI-compatible LLM + Tavily/Serper/DDG)
python main.py

# Perplexity backend (Sonar tier escalation)
python main_perplexity.py
```

Both expose the same `/research`, `/research/{job_id}`, and `/research/stream`
endpoints, so your client code works with either.

## Cost Estimates

| Depth | Typical Chains | Sources | Est. Cost | Time |
|-------|---------------|---------|-----------|------|
| scan | 2 | 5-10 | ~$0.05 | 10-15s |
| standard | 4 | 15-25 | ~$0.20 | 30-45s |
| deep | 6 | 25-40 | ~$0.80 | 1-2 min |
| exhaustive | 10 | 40-80 | ~$2.00+ | 3-5 min |

## License

MIT
