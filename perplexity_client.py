"""
Perplexity Sonar API Client
============================
Tiered search client that layers across Perplexity's model hierarchy:
  sonar (low)  →  sonar-pro (medium/high)  →  sonar-deep-research (exhaustive)

Supports search_context_size (low/medium/high), search_domain_filter,
search_recency_filter, search_mode (web/academic/sec), and reasoning_effort.
"""

import httpx
import json
from typing import Optional


class PerplexityClient:
    """Async Perplexity Sonar API client with tiered model routing."""

    BASE_URL = "https://api.perplexity.ai/v1/sonar"

    # Model tiers: map depth levels to Sonar models + context sizes
    TIER_CONFIG = {
        "scan": {
            "model": "sonar",
            "search_context_size": "low",
            "description": "Fast factual lookup, minimal cost",
        },
        "standard": {
            "model": "sonar",
            "search_context_size": "medium",
            "description": "Balanced cost/quality for moderate queries",
        },
        "deep": {
            "model": "sonar-pro",
            "search_context_size": "high",
            "description": "Multi-step Q&A with 2x sources, full context",
        },
        "exhaustive": {
            "model": "sonar-deep-research",
            "reasoning_effort": "high",
            "description": "Full deep research with reasoning, hundreds of sources",
        },
    }

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(
        self,
        query: str,
        tier: str = "standard",
        system_prompt: Optional[str] = None,
        search_domain_filter: Optional[list[str]] = None,
        search_recency_filter: Optional[str] = None,
        search_mode: Optional[str] = None,
        return_images: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Execute a search at the specified tier.

        Args:
            query: The search query or research question
            tier: scan | standard | deep | exhaustive
            system_prompt: Optional system message for response shaping
            search_domain_filter: List of domains to include/exclude (prefix with - to exclude)
            search_recency_filter: day | week | month | year
            search_mode: web | academic | sec
            return_images: Whether to include images in response
            temperature: LLM temperature (lower = more factual)
            max_tokens: Max output tokens

        Returns:
            dict with keys: content, citations, search_results, usage, model
        """
        config = self.TIER_CONFIG.get(tier)
        if not config:
            raise ValueError(f"Unknown tier: {tier}. Use: {list(self.TIER_CONFIG.keys())}")

        model = config["model"]

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": query})

        # Build request payload
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add web_search_options for non-deep-research models
        if model != "sonar-deep-research":
            web_search_options = {}
            if "search_context_size" in config:
                web_search_options["search_context_size"] = config["search_context_size"]
            if web_search_options:
                payload["web_search_options"] = web_search_options
        else:
            # Deep research supports reasoning_effort
            if "reasoning_effort" in config:
                payload["reasoning_effort"] = config["reasoning_effort"]

        # Add optional filters
        if search_domain_filter:
            payload["search_domain_filter"] = search_domain_filter
        if search_recency_filter:
            payload["search_recency_filter"] = search_recency_filter
        if search_mode:
            payload["search_mode"] = search_mode
        if return_images:
            payload["return_images"] = True

        # Execute request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Deep research can take minutes; set generous timeout
        timeout = 300.0 if model == "sonar-deep-research" else 60.0

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.BASE_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Parse response
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        return {
            "content": message.get("content", ""),
            "citations": data.get("citations", []),
            "search_results": data.get("search_results", []),
            "usage": data.get("usage", {}),
            "model": data.get("model", model),
            "tier": tier,
        }

    async def multi_tier_search(
        self,
        query: str,
        tiers: list[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> list[dict]:
        """
        Execute the same query across multiple tiers for comparison or
        progressive deepening. Returns results from all tiers.
        """
        if tiers is None:
            tiers = ["scan", "standard"]

        import asyncio
        tasks = [
            self.search(query, tier=t, system_prompt=system_prompt, **kwargs)
            for t in tiers
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)
