"""Plain-text helpers shared by every provider."""
from __future__ import annotations

import re
from html import unescape
from typing import Any, Dict, List


def html_to_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def extract_basic_skills(text: str) -> List[str]:
    vocab = [
        # AI / LLM
        "RAG", "LLM", "LangChain", "LangGraph", "Agent", "Vector Search",
        "Machine Learning", "PyTorch", "TensorFlow", "Dify", "Ollama",
        "OpenSearch", "Elasticsearch", "Qdrant", "FAISS",
        # Backend languages
        "Python", "Java", "C#", ".NET", "Go", "TypeScript", "JavaScript",
        "PHP", "Ruby", "Scala", "Kotlin",
        # Frontend
        "React", "Vue", "Angular",
        # API / Frameworks
        "FastAPI", "Spring Boot", "Spring Cloud", ".NET Core", "ASP.NET",
        # Cloud & Infra
        "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Jenkins",
        "Nginx", "Redis", "RabbitMQ",
        # Databases
        "SQL Server", "MySQL", "PostgreSQL", "MongoDB", "Oracle",
        # Microsoft ecosystem
        "SharePoint", "Office365", "Dynamics 365", "Power Platform",
        # Japanese market specific
        "JLPT", "N1", "N2", "N3", "日本語", "英語", "中国語",
        # BIM / Construction IT
        "BIM", "CAD",
        # Microservices / Architecture
        "microservices", "マイクロサービス", "オフショア", "offshore",
    ]
    text_l = (text or "").lower()
    return [skill for skill in vocab if skill.lower() in text_l]


def job_text(job: Dict[str, Any]) -> str:
    text = " ".join([
        str(job.get("title", "")),
        str(job.get("company", "")),
        str(job.get("location", "")),
        str(job.get("description", "")),
        " ".join(job.get("skills", []) or []),
    ])
    return text.lower()
