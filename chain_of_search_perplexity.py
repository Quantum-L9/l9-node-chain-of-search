"""
Chain-of-Search Engine — Perplexity Edition
============================================
Replaces the generic LLM+search implementation with Perplexity's tiered
Sonar API. Uses the same Decompose→Search→Evaluate→Gap-Fill→Synthesize
pipeline, but each step uses the appropriate Perplexity model tier.

Tier escalation strategy:
  Step 1 (Decompose):       sonar (low)    — fast sub-query generation
  Step 2 (Search):          sonar-pro (high) — deep parallel retrieval
  Step 3 (Evaluate):        sonar (medium)  — relevance scoring
  Step 4 (Gap Analysis):    sonar (medium)  — coverage assessment
  Step 5 (Synthesize):      sonar-deep-research — exhaustive final report

This mirrors the chain-of-search architecture from CoRAG (Microsoft, 2025)
while leveraging Perplexity's native search_context_size tiers for cost
optimization at each pipeline stage.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from perplexity_client import PerplexityClient


# ── Prompt Templates (7-Component Architecture) ─────────────────────
# Profile → Directive → Context → Workflow → Constraints → Output → Examples

DECOMPOSE_SYSTEM = """You are an expert research strategist. You decompose
complex questions into targeted, non-overlapping sub-queries for web search.
Return ONLY a JSON array of 3-6 query strings. No commentary."""

DECOMPOSE_USER = """Research question: {query}
Depth level: {depth}
Prior findings: {prior_findings}

Generate {n_queries} diverse sub-queries covering different facets:
definition, mechanism, comparison, evidence, counterargument, recent developments.
Each sub-query must be under 15 words. Include at least one targeting 2024-2026.
Return ONLY a JSON array."""

EVALUATE_SYSTEM = """You are a research relevance evaluator. Score results 0-10
and extract verifiable claims. Return ONLY valid JSON."""

EVALUATE_USER = """Research question: {query}
Sub-query: {subquery}

Perplexity returned this answer with {n_citations} citations:
---
{content}
---
Citations: {citations}

Evaluate and return JSON:
{{
  "relevance_score": 8,
  "key_claims": [
    {{"claim": "factual claim text", "citation_url": "source url"}}
  ],
  "coverage_gaps": ["topic not covered"],
  "sufficient": false
}}"""

GAP_SYSTEM = """You are a research coverage analyst. Identify missing information
and generate follow-up queries. Return ONLY valid JSON."""

GAP_USER = """Original question: {query}
Findings so far:
{findings}
Previous sub-queries: {previous}

Return JSON:
{{
  "gaps": ["gap1", "gap2"],
  "follow_up_queries": ["query1", "query2"],
  "coverage_pct": 0.65,
  "stop": false
}}"""

SYNTHESIZE_SYSTEM = """You are an expert research analyst producing comprehensive,
citation-backed research briefs. Every factual claim must cite its source URL.
Use ## section headers. Flag contradictions between sources explicitly.
Write in active voice with clear, direct language."""

SYNTHESIZE_USER = """Research question: {query}
Depth: {depth}
Date: {date}
Sources consulted: {n_sources}

All findings with citations:
{findings}

Produce a structured research brief ({min_words}+ words) in {output_format} format.
Open with a 2-sentence direct answer. Organize into thematic sections.
Close with knowledge gaps and suggested follow-up questions."""


DEPTH_CONFIG = {
    "scan":      {"max_chains": 2, "queries_per_step": 3, "min_words": 500},
    "standard":  {"max_chains": 4, "queries_per_step": 4, "min_words": 1200},
    "deep":      {"max_chains": 6, "queries_per_step": 5, "min_words": 2500},
    "exhaustive":{"max_chains": 10,"queries_per_step": 6, "min_words": 4000},
}


class ChainOfSearchPerplexity:
    """Chain-of-search engine using Perplexity's tiered Sonar API."""

    def __init__(self, api_key: str, domain_filter: list[str] = None):
        self.client = PerplexityClient(api_key)
        self.domain_filter = domain_filter  # e.g. ["arxiv.org", "github.com"]

    async def run(self, job_id: str, req, jobs: dict):
        """Execute full chain-of-search pipeline with tier escalation."""
        try:
            jobs[job_id]["status"] = "searching"
            depth_cfg = DEPTH_CONFIG.get(req.depth, DEPTH_CONFIG["standard"])
            max_chains = min(req.max_chains, depth_cfg["max_chains"])

            all_findings = []
            all_citations = []
            all_subqueries = []
            prior_text = "None yet."

            for chain_step in range(max_chains):
                jobs[job_id]["progress"] = round(chain_step / max_chains, 2)
                jobs[job_id]["chains_completed"] = chain_step

                # ── Step A: Decompose (sonar/low — cheap & fast) ──
                if chain_step == 0:
                    subqueries = await self._decompose(
                        req.query, req.depth, prior_text,
                        depth_cfg["queries_per_step"]
                    )
                else:
                    gap_result = await self._analyze_gaps(
                        req.query, prior_text, all_subqueries
                    )
                    if gap_result.get("stop", False) or gap_result.get("coverage_pct", 0) > 0.9:
                        break
                    subqueries = gap_result.get("follow_up_queries", [])
                    if not subqueries:
                        break

                all_subqueries.extend(subqueries)

                # ── Step B: Search (sonar-pro/high — deep retrieval) ──
                search_tasks = []
                for sq in subqueries:
                    jobs[job_id]["current_subquery"] = sq
                    search_tasks.append(
                        self.client.search(
                            query=sq,
                            tier="deep",  # sonar-pro with high context
                            search_domain_filter=self.domain_filter,
                            search_recency_filter=req.recency_filter if hasattr(req, "recency_filter") else None,
                        )
                    )

                results = await asyncio.gather(*search_tasks, return_exceptions=True)

                # ── Step C: Evaluate (sonar/medium — balanced) ──
                for sq, result in zip(subqueries, results):
                    if isinstance(result, Exception):
                        continue

                    evaluated = await self._evaluate(
                        req.query, sq, result["content"],
                        result["citations"]
                    )

                    for claim_obj in evaluated.get("key_claims", []):
                        claim = claim_obj if isinstance(claim_obj, str) else claim_obj.get("claim", "")
                        url = claim_obj.get("citation_url", "") if isinstance(claim_obj, dict) else ""
                        all_findings.append(f"- {claim} [Source: {url}]")

                    for cite in result.get("citations", []):
                        if cite not in all_citations:
                            all_citations.append(cite)

                jobs[job_id]["sources_found"] = len(all_citations)
                prior_text = "\n".join(all_findings[-40:])

                if len(all_citations) >= req.max_sources:
                    break

            # ── Step D: Synthesize (sonar-deep-research — exhaustive) ──
            jobs[job_id]["status"] = "synthesizing"
            jobs[job_id]["progress"] = 0.9

            brief = await self._synthesize(
                query=req.query,
                depth=req.depth,
                findings="\n".join(all_findings),
                n_sources=len(all_citations),
                min_words=depth_cfg["min_words"],
                output_format=req.output_format,
            )

            jobs[job_id]["status"] = "complete"
            jobs[job_id]["progress"] = 1.0
            jobs[job_id]["result"] = {
                "brief": brief,
                "citations": all_citations,
                "chains_executed": min(chain_step + 1, max_chains),
                "subqueries_used": all_subqueries,
            }

        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)

    async def _decompose(self, query, depth, prior, n_queries):
        """Use sonar (low context) for fast sub-query generation."""
        user_msg = DECOMPOSE_USER.format(
            query=query, depth=depth, prior_findings=prior, n_queries=n_queries
        )
        result = await self.client.search(
            query=user_msg,
            tier="scan",  # sonar with low context
            system_prompt=DECOMPOSE_SYSTEM,
            temperature=0.5,
        )
        try:
            return json.loads(result["content"])
        except json.JSONDecodeError:
            lines = [l.strip().strip('"').strip("- ") for l in result["content"].split("\n") if l.strip()]
            return lines[:n_queries]

    async def _evaluate(self, query, subquery, content, citations):
        """Use sonar (medium context) for balanced relevance evaluation."""
        user_msg = EVALUATE_USER.format(
            query=query, subquery=subquery, content=content[:3000],
            n_citations=len(citations), citations=json.dumps(citations[:10]),
        )
        result = await self.client.search(
            query=user_msg,
            tier="standard",  # sonar with medium context
            system_prompt=EVALUATE_SYSTEM,
            temperature=0.1,
        )
        try:
            return json.loads(result["content"])
        except json.JSONDecodeError:
            return {"key_claims": [], "coverage_gaps": [], "sufficient": False}

    async def _analyze_gaps(self, query, findings, previous):
        """Use sonar (medium context) for gap analysis."""
        user_msg = GAP_USER.format(
            query=query, findings=findings[:3000], previous=json.dumps(previous),
        )
        result = await self.client.search(
            query=user_msg,
            tier="standard",
            system_prompt=GAP_SYSTEM,
            temperature=0.3,
        )
        try:
            return json.loads(result["content"])
        except json.JSONDecodeError:
            return {"stop": True}

    async def _synthesize(self, query, depth, findings, n_sources, min_words, output_format):
        """Use sonar-deep-research for exhaustive final synthesis."""
        user_msg = SYNTHESIZE_USER.format(
            query=query, depth=depth,
            date=datetime.utcnow().strftime("%Y-%m-%d"),
            n_sources=n_sources,
            findings=findings[:15000],
            min_words=min_words,
            output_format=output_format,
        )
        result = await self.client.search(
            query=user_msg,
            tier="exhaustive",  # sonar-deep-research
            system_prompt=SYNTHESIZE_SYSTEM,
            max_tokens=8192,
        )
        return result["content"]
