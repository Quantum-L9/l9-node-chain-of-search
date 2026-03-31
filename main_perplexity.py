#!/usr/bin/env python3
"""
Chain-of-Search Microservice — Perplexity Edition
===================================================
Drop-in replacement for main.py that uses Perplexity's Sonar API
with tiered model escalation instead of generic LLM+search.

Usage:
  export PERPLEXITY_API_KEY=pplx-xxxxx
  python main_perplexity.py
"""

import os
import time
import uuid
import json
import asyncio

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from chain_of_search_perplexity import ChainOfSearchPerplexity


app = FastAPI(
    title="Chain-of-Search (Perplexity Edition)",
    version="0.2.0",
    description="Iterative chain-of-retrieval via Perplexity Sonar API tiers",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
if not API_KEY:
    raise RuntimeError("Set PERPLEXITY_API_KEY environment variable")

jobs: dict = {}


class ResearchRequest(BaseModel):
    query: str = Field(..., description="The research question")
    depth: str = Field("standard", description="scan | standard | deep | exhaustive")
    max_chains: int = Field(6, ge=1, le=20)
    max_sources: int = Field(30, ge=5, le=100)
    output_format: str = Field("markdown", description="markdown | json | html")
    domain_filter: Optional[list[str]] = Field(None, description="Domains to include (or -exclude)")
    recency_filter: Optional[str] = Field(None, description="day | week | month | year")
    search_mode: Optional[str] = Field(None, description="web | academic | sec")


class ResearchStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    chains_completed: int
    sources_found: int
    current_subquery: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


@app.post("/research", response_model=ResearchStatus)
async def start_research(req: ResearchRequest, bg: BackgroundTasks):
    job_id = str(uuid.uuid4())[:12]
    engine = ChainOfSearchPerplexity(API_KEY, domain_filter=req.domain_filter)
    jobs[job_id] = {
        "status": "queued", "progress": 0.0, "chains_completed": 0,
        "sources_found": 0, "current_subquery": None,
        "result": None, "error": None, "start_time": time.time(),
    }
    bg.add_task(engine.run, job_id, req, jobs)
    return ResearchStatus(job_id=job_id, status="queued", progress=0.0, chains_completed=0, sources_found=0)


@app.get("/research/{job_id}", response_model=ResearchStatus)
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    j = jobs[job_id]
    return ResearchStatus(
        job_id=job_id,
        elapsed_seconds=time.time() - j.get("start_time", time.time()),
        **{k: v for k, v in j.items() if k != "start_time"},
    )


@app.post("/research/stream")
async def stream_research(req: ResearchRequest):
    async def sse():
        job_id = str(uuid.uuid4())[:12]
        engine = ChainOfSearchPerplexity(API_KEY, domain_filter=req.domain_filter)
        jobs[job_id] = {
            "status": "queued", "progress": 0.0, "chains_completed": 0,
            "sources_found": 0, "current_subquery": None,
            "result": None, "error": None, "start_time": time.time(),
        }
        task = asyncio.create_task(engine.run(job_id, req, jobs))
        while not task.done():
            j = jobs[job_id]
            yield f"data: {json.dumps({'job_id': job_id, 'status': j['status'], 'progress': j['progress'], 'current_subquery': j['current_subquery']})}\n\n"
            await asyncio.sleep(1.5)
        j = jobs[job_id]
        yield f"data: {json.dumps({'job_id': job_id, 'status': j['status'], 'progress': 1.0, 'result': j['result']})}\n\n"
    return StreamingResponse(sse(), media_type="text/event-stream")


@app.get("/tiers")
async def list_tiers():
    """Show available Perplexity tier configurations."""
    from perplexity_client import PerplexityClient
    return PerplexityClient.TIER_CONFIG


@app.get("/health")
async def health():
    return {"status": "ok", "backend": "perplexity-sonar", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    uvicorn.run("main_perplexity:app", host="0.0.0.0", port=8000, reload=True)
