"""Built-in sample postings for demos and offline runs."""
from __future__ import annotations

from typing import Any, Dict, List

from .models import make_job


def seed_jobs() -> List[Dict[str, Any]]:
    """Return a small deterministic dataset for smoke tests and examples."""
    return [
        make_job(
            title="AI Platform Engineer",
            company="Tokyo GenAI Lab",
            location="Tokyo, Japan",
            description="Build internal agents and retrieval pipelines for enterprise clients.",
            source="seed",
            skills=["Python", "RAG", "FastAPI", "Agent"],
            remote=False,
        ),
        make_job(
            title="Applied Scientist",
            company="Kyoto Intelligence",
            location="Kyoto, Japan",
            description="Research-oriented GenAI role using LangChain and vector DBs.",
            source="seed",
            skills=["Python", "LangChain", "Qdrant", "RAG"],
            remote=True,
        ),
        make_job(
            title="Full-Stack LLM Engineer",
            company="Osaka AI Works",
            location="Osaka, Japan",
            description="Ship LLM backed products using TypeScript/React frontends.",
            source="seed",
            skills=["Python", "TypeScript", "React", "Agent"],
            remote=True,
        ),
        make_job(
            title="Machine Learning Engineer",
            company="Sapporo Robotics",
            location="Remote (Japan)",
            description="Expand ML platforms with Kubernetes and AWS infrastructure.",
            source="seed",
            skills=["Python", "AWS", "Kubernetes", "FastAPI"],
            remote=True,
        ),
    ]
