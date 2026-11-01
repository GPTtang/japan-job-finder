from __future__ import annotations

from typing import Dict, List

from .signals import has_any_term, has_term


# Roles: English + Japanese variants
_ROLE_VOCAB = [
    # AI / LLM
    "AI Engineer", "LLM Engineer", "Applied AI Engineer", "RAG Engineer",
    "ML Engineer", "Machine Learning Engineer", "Data Engineer", "Data Scientist",
    "AI Researcher", "Prompt Engineer",
    # Backend / Platform
    "Backend Engineer", "Platform Engineer", "Software Engineer",
    "Full-Stack Engineer", "Full Stack Engineer", "Frontend Engineer",
    "Infrastructure Engineer", "Cloud Engineer", "DevOps Engineer",
    # Management & Consulting
    "Project Manager", "Product Manager", "IT Consultant", "DX Consultant",
    "System Architect", "Solution Architect", "Technical Lead",
    # Japan-specific
    "Bridge SE", "ブリッジSE", "ブリッジエンジニア",
    "システムエンジニア", "プロジェクトマネージャー", "プロダクトマネージャー",
    "開発エンジニア", "インフラエンジニア", "クラウドエンジニア",
    "ITコンサルタント", "アーキテクト",
]

# Skills: English + Japanese variants
_SKILL_VOCAB = [
    # AI / LLM
    "Python", "RAG", "LLM", "LangChain", "LangGraph", "Agent",
    "Vector Search", "Machine Learning", "FastAPI",
    "OpenSearch", "Elasticsearch", "Qdrant", "FAISS",
    "PyTorch", "TensorFlow", "Dify", "Ollama",
    # Backend languages
    "Java", "C#", ".NET", ".NET Core", "Go", "TypeScript", "JavaScript",
    "PHP", "Ruby", "Kotlin", "Scala",
    # Frontend
    "React", "Vue", "Angular",
    # Cloud & Infra
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Jenkins",
    "Nginx", "Redis", "RabbitMQ",
    # Databases
    "SQL Server", "MySQL", "PostgreSQL", "MongoDB", "Oracle",
    # Microsoft ecosystem
    "SharePoint", "Office365", "Dynamics 365", "Power Platform",
    # Domain
    "BIM", "CAD", "SAP", "ERP",
    # Japanese market
    "オフショア", "offshore", "マイクロサービス", "microservices",
]

# JLPT level keywords
_JLPT_MAP = {
    "n1": "N1", "jlpt n1": "N1", "日本語n1": "N1",
    "n2": "N2", "jlpt n2": "N2", "日本語n2": "N2",
    "n3": "N3", "jlpt n3": "N3",
    "business japanese": "N2", "ビジネス日本語": "N2",
    "native japanese": "N1", "日本語ネイティブ": "N1",
    "conversational japanese": "N3", "日常会話": "N3",
}

def parse_user_query(query: str) -> Dict[str, object]:
    text = query.strip()
    text_l = text.lower()

    roles = [r for r in _ROLE_VOCAB if has_term(text, r)]

    # Each group is a set of aliases for the same place.
    # When any alias is detected we add all canonical forms,
    # so the location filter matches both English and CJK job listings.
    _LOCATION_GROUPS = [
        ["Tokyo", "東京", "东京"],
        ["Japan", "日本"],
        ["Remote", "リモート", "远程"],
        ["Osaka", "大阪", "大阪市"],
        ["Kyoto", "京都", "京都市"],
        ["Yokohama", "横浜"],
    ]
    seen_locs: set = set()
    location_hits = []
    for group in _LOCATION_GROUPS:
        if has_any_term(text, group):
            for canonical in group:
                if canonical.lower() not in seen_locs:
                    seen_locs.add(canonical.lower())
                    location_hits.append(canonical)

    skills = [s for s in _SKILL_VOCAB if has_term(text, s)]

    keyword_terms = list({
        t for t in _ROLE_VOCAB + _SKILL_VOCAB + [
            "startup", "product", "backend", "platform", "applied ai",
            "DX", "SES", "SIer", "consulting",
        ]
        if has_term(text, t)
    })

    remote_preference = None
    if "remote only" in text_l or "fully remote" in text_l or "纯远程" in text_l:
        remote_preference = "only"
    elif "remote" in text_l or "远程" in text_l or "リモート" in text_l:
        remote_preference = "prefer"

    # JLPT level declared in query — prefer the highest explicit level found
    # (e.g. "I have N2, working towards N1" → N2 is the current cert)
    _JLPT_RANK_MAP = {"N1": 1, "N2": 2, "N3": 3}
    jlpt_hits = [level for pattern, level in _JLPT_MAP.items() if has_term(text, pattern)]
    jlpt_level = min(jlpt_hits, key=lambda x: _JLPT_RANK_MAP[x]) if jlpt_hits else None

    # Chinese speaker flag
    is_chinese_speaker = has_any_term(text, [
        "chinese speaker", "中文母语", "native chinese", "中国人",
        "chinese native", "mandarin native",
    ])

    return {
        "raw_query": text,
        "target_roles": roles,
        "locations": location_hits,
        "skills": skills,
        "keyword_terms": keyword_terms,
        "remote_preference": remote_preference,
        "jlpt_level": jlpt_level,
        "is_chinese_speaker": is_chinese_speaker,
    }
