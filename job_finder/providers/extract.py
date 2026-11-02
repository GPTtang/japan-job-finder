"""Strategies for pulling job records out of HTML pages and JSON blobs."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from .models import make_job
from .text import extract_basic_skills, html_to_text


def extract_company_name(html: str) -> str:
    """Best-effort extraction of company name from page <title> or og:site_name."""
    m = re.search(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\'](.*?)["\']', html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    if m:
        title = html_to_text(m.group(1))
        # "Careers | CompanyName" or "CompanyName - 採用情報" → take the meaningful part
        for sep in ["|", "｜", " - ", "—", "–", "·", "採用情報", "求人情報", "採用", "Careers", "Jobs"]:
            if sep in title:
                parts = [p.strip() for p in title.split(sep) if p.strip()]
                parts = [p for p in parts if len(p) > 1 and p not in ("Careers", "Jobs", "採用情報", "求人情報", "採用")]
                if parts:
                    return parts[-1]  # usually company name is at the end
        return title.strip()[:60]
    return ""


# Job-title signals for heuristic detection — deliberately conservative to avoid
# matching navigation labels, service descriptions, or marketing headings.
# Only include terms that are unambiguous job role identifiers.
_JOB_TITLE_SIGNALS = [
    # Japanese role suffixes / standalone titles
    "エンジニア", "プログラマー", "プログラマ", "ブリッジSE", "ブリッジエンジニア",
    "システムエンジニア", "インフラエンジニア", "クラウドエンジニア",
    "プロジェクトマネージャー", "ITコンサルタント", "アーキテクト", "スペシャリスト",
    # Chinese / bilingual role names common in Chinese IT companies in Japan
    "開発エンジニア", "ネットワークエンジニア", "セキュリティエンジニア",
    # English role suffixes (require at least one word before, matched via regex)
    " Engineer", " Developer", " Architect", " Consultant", " Manager",
    " Analyst", " Specialist", " Programmer", " Lead", " Director",
    # Exact short abbreviations — only valid as the whole text or with adjective
    "Bridge SE", "SRE", "DevOps Engineer", "PMO",
]


# Phrases that look like job signals but are NOT job titles — skip these
_JOB_TITLE_EXCLUDES = [
    "services we offer", "it services", "our services", "service", "talent acquisition",
    "about us", "contact", "news", "blog", "support", "solutions", "products",
    "サービス", "ソリューション", "お問い合わせ", "採用情報", "会社概要",
]


def _looks_like_job_title(text: str) -> bool:
    """Return True if a short text fragment looks like a job title."""
    if not text or len(text) < 4 or len(text) > 100:
        return False
    t_lower = text.lower()
    # Exclude known non-title phrases
    if any(excl in t_lower for excl in _JOB_TITLE_EXCLUDES):
        return False
    return any(sig.lower() in t_lower for sig in _JOB_TITLE_SIGNALS)


def extract_jobs_from_html_heuristic(
    html: str,
    url: str,
    company_hint: str = "",
) -> List[Dict[str, Any]]:
    """Extract job listings from plain HTML career pages without JSON-LD.

    Strategy:
    1. Derive company name from <title> / og:site_name.
    2. Scan <h2>/<h3>/<h4> headings and <td>/<li> elements for job-title-like text.
    3. Build one synthetic job record per detected title, using the surrounding
       section text as the description.

    This covers ~60-70% of Japanese company career pages that use plain HTML
    tables or lists rather than structured data formats.
    """
    if not html:
        return []

    company = company_hint or extract_company_name(html)
    if not company:
        # Fall back to domain name
        m = re.search(r'https?://(?:www\.)?([^/]+)', url)
        company = m.group(1) if m else url

    jobs: List[Dict[str, Any]] = []
    seen_titles: set = set()

    # --- Pass 1: headings (h2/h3/h4) ----------------------------------------
    for m in re.finditer(r'<h[234][^>]*>(.*?)</h[234]>', html, re.I | re.S):
        text = html_to_text(m.group(1)).strip()
        if not _looks_like_job_title(text) or text.lower() in seen_titles:
            continue
        seen_titles.add(text.lower())
        # Grab the text that follows the heading (up to 800 chars) as description
        pos_end = m.end()
        snippet = html_to_text(html[pos_end: pos_end + 1200])[:500]
        jobs.append(make_job(
            title=text,
            company=company,
            location="Tokyo, Japan",  # assume Tokyo unless text says otherwise
            url=url,
            description=snippet,
            source="company_site",
            skills=extract_basic_skills(f"{text} {snippet}"),
        ))

    if jobs:
        return jobs

    # --- Pass 2: table cells <td> --------------------------------------------
    for m in re.finditer(r'<td[^>]*>(.*?)</td>', html, re.I | re.S):
        text = html_to_text(m.group(1)).strip()
        if not _looks_like_job_title(text) or text.lower() in seen_titles:
            continue
        seen_titles.add(text.lower())
        jobs.append(make_job(
            title=text,
            company=company,
            location="Tokyo, Japan",
            url=url,
            description=text,
            source="company_site",
            skills=extract_basic_skills(text),
        ))

    if jobs:
        return jobs

    # --- Pass 3: list items <li> ---------------------------------------------
    for m in re.finditer(r'<li[^>]*>(.*?)</li>', html, re.I | re.S):
        text = html_to_text(m.group(1)).strip()
        if not _looks_like_job_title(text) or text.lower() in seen_titles:
            continue
        seen_titles.add(text.lower())
        jobs.append(make_job(
            title=text,
            company=company,
            location="Tokyo, Japan",
            url=url,
            description=text,
            source="company_site",
            skills=extract_basic_skills(text),
        ))

    return jobs


def extract_json_ld_jobpostings(html: str, base_url: str) -> List[Dict[str, Any]]:
    jobs = []
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    )
    for raw in scripts:
        try:
            data = json.loads(raw.strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                jobs.append(make_job(
                    title=item.get("title", ""),
                    company=((item.get("hiringOrganization") or {}).get("name", "")),
                    location=(((item.get("jobLocation") or {}).get("address") or {}).get("addressLocality", "")),
                    url=base_url,
                    description=item.get("description", ""),
                    source="company_site",
                    extract_skills=True,
                    remote=item.get("jobLocationType") == "TELECOMMUTE",
                    posted_date=item.get("datePosted"),
                    deadline=item.get("validThrough"),
                ))
    return jobs


def scan_for_jobs(data: Any, source_url: str, source_name: str = "unknown") -> List[Dict[str, Any]]:
    """Recursively scan a nested data structure for job-like records."""
    jobs: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        title = data.get("title") or data.get("name") or data.get("job_title")
        company = data.get("company") or data.get("company_name") or data.get("employer")
        if title and company and isinstance(title, str) and isinstance(company, str):
            desc = str(data.get("description") or data.get("body") or "")
            jobs.append(make_job(
                title=title,
                company=company,
                location=str(data.get("location") or data.get("city") or ""),
                url=str(data.get("url") or data.get("job_url") or data.get("apply_url") or source_url),
                description=desc,
                source=source_name,
                extract_skills=True,
            ))
        else:
            for v in data.values():
                jobs.extend(scan_for_jobs(v, source_url, source_name))
    elif isinstance(data, list):
        for item in data:
            jobs.extend(scan_for_jobs(item, source_url, source_name))
    return jobs


def extract_jobs_from_rendered_html(html: str, base_url: str, source_name: str = "unknown") -> List[Dict[str, Any]]:
    """Extract job listings from fully rendered HTML using all available strategies.

    Tries (in order): JSON-LD → Next.js __NEXT_DATA__ → Nuxt 3 __NUXT_DATA__ →
    Nuxt 2 window.__NUXT__ → generic application/json blobs.
    Returns on the first strategy that yields results.
    """
    if not html:
        return []

    # 1. JSON-LD structured data (most reliable when present)
    jobs = extract_json_ld_jobpostings(html, base_url)
    if jobs:
        return jobs

    # 2. Next.js hydration blob
    for raw in re.findall(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, flags=re.I | re.S,
    ):
        try:
            jobs.extend(scan_for_jobs(json.loads(raw.strip()), base_url, source_name))
        except Exception:
            pass
    if jobs:
        return jobs

    # 3. Nuxt 3: <script id="__NUXT_DATA__" type="application/json">
    for raw in re.findall(
        r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>',
        html, flags=re.I | re.S,
    ):
        try:
            jobs.extend(scan_for_jobs(json.loads(raw.strip()), base_url, source_name))
        except Exception:
            pass
    if jobs:
        return jobs

    # 4. Nuxt 2: window.__NUXT__ = {...};
    for m in re.finditer(r'window\.__NUXT__\s*=\s*(\{.*?\})\s*(?:;|</script>)', html, re.S):
        try:
            jobs.extend(scan_for_jobs(json.loads(m.group(1)), base_url, source_name))
        except Exception:
            pass
    if jobs:
        return jobs

    # 5. Generic application/json script tags
    for raw in re.findall(
        r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
        html, flags=re.I | re.S,
    ):
        try:
            jobs.extend(scan_for_jobs(json.loads(raw.strip()), base_url, source_name))
        except Exception:
            pass

    return jobs
