from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from html import unescape
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin

import requests

from .guard import guard


# ---------------------------------------------------------------------------
# Data classes — defined first so every function below can reference them
# ---------------------------------------------------------------------------

@dataclass
class FetchIssue:
    provider: str
    message: str
    source_ref: str = ""
    severity: str = "warning"
    retryable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    provider: str
    jobs: List[Dict[str, Any]] = field(default_factory=list)
    issues: List[FetchIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when the fetch completed without any error-severity issues.

        An empty ``jobs`` list is *not* a failure — the source may simply have
        no open positions right now.  Callers that care about emptiness should
        check ``len(result.jobs) > 0`` separately.
        """
        return not any(i.severity == "error" for i in self.issues)


# ---------------------------------------------------------------------------
# Headless browser support (optional — requires: pip install playwright
#                                                playwright install chromium)
# ---------------------------------------------------------------------------

def _playwright_get_text(
    url: str,
    *,
    timeout_ms: int = 30_000,
    wait_until: str = "networkidle",
) -> tuple[Optional[str], List["FetchIssue"]]:
    """Fetch ``url`` with a headless Chromium browser and return the rendered HTML.

    Returns ``(None, issues)`` if Playwright is not installed or the fetch fails,
    so callers can degrade gracefully without crashing.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import]
    except ImportError:
        return None, [FetchIssue(
            provider="browser",
            source_ref=url,
            message=(
                "Playwright not installed — JS rendering unavailable. "
                "To enable: pip install playwright && playwright install chromium"
            ),
            severity="warning",
            retryable=False,
        )]

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="ja-JP",
            )
            page = ctx.new_page()
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            html = page.content()
            browser.close()
            return html, []
    except Exception as exc:  # noqa: BLE001
        return None, [FetchIssue(
            provider="browser",
            source_ref=url,
            message=f"Playwright error: {exc}",
            severity="error",
            retryable=False,
        )]




def make_job(
    *,
    title: str,
    company: str,
    location: str = "",
    url: str = "",
    description: str = "",
    source: str = "",
    skills: Optional[List[str]] = None,
    extract_skills: bool = False,
    remote: Optional[bool] = None,
    posted_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a job record.

    ``description`` may be raw HTML or text from an untrusted source: it passes
    through the integrity gate, which stores the cleaned text and a verdict in
    ``guard``. With ``extract_skills`` the skill list is read from that cleaned
    text, so hidden keyword stuffing cannot inflate the match.
    """
    checked = guard(description)
    if skills is None and extract_skills:
        skills = _extract_basic_skills(checked.text)
    return {
        "title": title or "",
        "company": company or "",
        "location": location or "",
        "url": url or "",
        "description": checked.text,
        "source": source or "",
        "skills": skills or [],
        "remote": remote,
        "posted_date": posted_date,
        "guard": checked.verdict,
    }


def _http_get(
    url: str,
    *,
    provider: str,
    timeout_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
) -> Tuple[Optional[requests.Response], List[FetchIssue]]:
    issues: List[FetchIssue] = []
    attempts = max_retries + 1

    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                url,
                timeout=timeout_seconds,
                headers={"User-Agent": "job-finder-skill/1.2"},
            )
        except requests.RequestException as exc:
            retryable = attempt < attempts
            issues.append(FetchIssue(
                provider=provider,
                source_ref=url,
                message=f"Network error on attempt {attempt}/{attempts}: {exc}",
                severity="error" if not retryable else "warning",
                retryable=retryable,
                details={"attempt": attempt, "attempts": attempts},
            ))
            if retryable:
                time.sleep(retry_backoff_seconds)
                continue
            return None, issues

        if response.status_code >= 500 and attempt < attempts:
            issues.append(FetchIssue(
                provider=provider,
                source_ref=url,
                message=f"HTTP {response.status_code} on attempt {attempt}/{attempts}",
                severity="warning",
                retryable=True,
                details={"attempt": attempt, "attempts": attempts},
            ))
            time.sleep(retry_backoff_seconds)
            continue

        return response, issues

    return None, issues


def _safe_get_json(
    url: str,
    *,
    provider: str,
    timeout_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
) -> tuple[Optional[Any], List[FetchIssue]]:
    response, issues = _http_get(
        url,
        provider=provider,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    if response is None:
        return None, issues

    if response.status_code >= 400:
        issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message=f"HTTP {response.status_code}",
            severity="error" if response.status_code >= 500 else "warning",
            retryable=response.status_code >= 500,
        ))
        return None, issues

    try:
        return response.json(), issues
    except ValueError:
        issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="Response was not valid JSON",
            severity="error",
            retryable=False,
        ))
        return None, issues


def _safe_get_text(
    url: str,
    *,
    provider: str,
    timeout_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
) -> tuple[Optional[str], List[FetchIssue]]:
    response, issues = _http_get(
        url,
        provider=provider,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    if response is None:
        return None, issues

    if response.status_code >= 400:
        issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message=f"HTTP {response.status_code}",
            severity="error" if response.status_code >= 500 else "warning",
            retryable=response.status_code >= 500,
        ))
        return None, issues

    # Detect encoding robustly — requests defaults to ISO-8859-1 for text/html
    # which breaks Japanese (UTF-8) pages.  Priority:
    #   1. charset declared in Content-Type header
    #   2. charset declared in <meta> tag
    #   3. UTF-8 (safe fallback for most modern pages)
    content_type = response.headers.get("content-type", "")
    ct_charset = re.search(r'charset=([^\s;]+)', content_type, re.I)
    if ct_charset:
        encoding = ct_charset.group(1).strip()
    else:
        raw = response.content
        meta_charset = re.search(
            rb'<meta[^>]+charset=["\']?([a-zA-Z0-9_\-]+)',
            raw[:4096], re.I,
        )
        encoding = meta_charset.group(1).decode("ascii") if meta_charset else "utf-8"

    try:
        return response.content.decode(encoding, errors="replace"), issues
    except (LookupError, UnicodeDecodeError):
        return response.content.decode("utf-8", errors="replace"), issues


def _html_to_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _extract_basic_skills(text: str) -> List[str]:
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


def _job_text(job: Dict[str, Any]) -> str:
    text = " ".join([
        str(job.get("title", "")),
        str(job.get("company", "")),
        str(job.get("location", "")),
        str(job.get("description", "")),
        " ".join(job.get("skills", []) or []),
    ])
    return text.lower()


def _apply_source_filters(
    jobs: List[Dict[str, Any]],
    filters: Dict[str, Any] | None,
    provider: str,
) -> tuple[List[Dict[str, Any]], List[FetchIssue]]:
    if not filters:
        return jobs, []

    issues: List[FetchIssue] = []
    filtered = jobs

    keywords = filters.get("keywords") or []
    if keywords:
        keywords_l = [k.lower() for k in keywords]
        filtered = [
            job for job in filtered
            if any(k in _job_text(job) for k in keywords_l)
        ]

    locations = filters.get("locations") or []
    if locations:
        locations_l = [loc.lower() for loc in locations]
        filtered = [
            job for job in filtered
            if not str(job.get("location", "")).strip()  # no location set → keep
            or any(loc in str(job.get("location", "")).lower() for loc in locations_l)
        ]

    if filters.get("remote_only"):
        filtered = [job for job in filtered if job.get("remote") is True]
    elif filters.get("remote_preferred"):
        remote_jobs = [job for job in filtered if job.get("remote") is True]
        non_remote_jobs = [job for job in filtered if job.get("remote") is not True]
        filtered = remote_jobs + non_remote_jobs

    if not filtered and jobs:
        issues.append(FetchIssue(
            provider=provider,
            message="Provider-level filters removed all fetched jobs",
            severity="warning",
            retryable=False,
            details={"filters": filters, "original_count": len(jobs)},
        ))

    return filtered, issues


def fetch_greenhouse(token: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    provider = "greenhouse"
    fetch_options = fetch_options or {}
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    data, issues = _safe_get_json(
        url,
        provider=provider,
        timeout_seconds=fetch_options.get("timeout_seconds", 15),
        max_retries=fetch_options.get("max_retries", 1),
        retry_backoff_seconds=fetch_options.get("retry_backoff_seconds", 0.5),
    )
    result = FetchResult(provider=provider, issues=issues)

    if not data:
        return result

    jobs = []
    for item in data.get("jobs", []):
        content = item.get("content", "") or ""
        location_name = (item.get("location") or {}).get("name", "")
        jobs.append(make_job(
            title=item.get("title", ""),
            company=token,
            location=location_name,
            url=item.get("absolute_url", ""),
            description=content,
            source=provider,
            extract_skills=True,
            remote="remote" in location_name.lower(),
            posted_date=item.get("updated_at") or item.get("created_at"),
        ))

    if not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="No jobs returned from source",
            severity="warning",
            retryable=False,
        ))
    result.jobs = jobs
    return result


def fetch_lever(company: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    provider = "lever"
    fetch_options = fetch_options or {}
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    data, issues = _safe_get_json(
        url,
        provider=provider,
        timeout_seconds=fetch_options.get("timeout_seconds", 15),
        max_retries=fetch_options.get("max_retries", 1),
        retry_backoff_seconds=fetch_options.get("retry_backoff_seconds", 0.5),
    )
    result = FetchResult(provider=provider, issues=issues)

    if not data:
        return result

    jobs = []
    for item in data:
        categories = item.get("categories", {}) or {}
        location = categories.get("location", "") or ""
        lists = item.get("lists") or []
        list_text = lists[0].get("text", "") if lists else ""
        raw_desc = " ".join([
            item.get("descriptionPlain", "") or "",
            list_text,
        ])
        jobs.append(make_job(
            title=item.get("text", ""),
            company=company,
            location=location,
            url=item.get("hostedUrl", ""),
            description=raw_desc,
            source=provider,
            extract_skills=True,
            remote="remote" in location.lower(),
            posted_date=item.get("createdAt"),
        ))

    if not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="No jobs returned from source",
            severity="warning",
            retryable=False,
        ))
    result.jobs = jobs
    return result


def fetch_ashby(board: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    provider = "ashby"
    fetch_options = fetch_options or {}
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
    data, issues = _safe_get_json(
        url,
        provider=provider,
        timeout_seconds=fetch_options.get("timeout_seconds", 15),
        max_retries=fetch_options.get("max_retries", 1),
        retry_backoff_seconds=fetch_options.get("retry_backoff_seconds", 0.5),
    )
    result = FetchResult(provider=provider, issues=issues)

    if not data:
        return result

    jobs = []
    for item in data.get("jobs", []):
        desc = item.get("descriptionPlain", "") or item.get("descriptionHtml", "") or ""
        location = item.get("location", "") or ""
        jobs.append(make_job(
            title=item.get("title", ""),
            company=board,
            location=location,
            url=item.get("jobUrl", ""),
            description=desc,
            source=provider,
            extract_skills=True,
            remote="remote" in location.lower(),
            posted_date=item.get("publishedDate"),
        ))

    if not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="No jobs returned from source",
            severity="warning",
            retryable=False,
        ))
    result.jobs = jobs
    return result


def _extract_company_name_from_html(html: str) -> str:
    """Best-effort extraction of company name from page <title> or og:site_name."""
    m = re.search(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\'](.*?)["\']', html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    if m:
        title = _html_to_text(m.group(1))
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


def _extract_jobs_from_html_heuristic(
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

    company = company_hint or _extract_company_name_from_html(html)
    if not company:
        # Fall back to domain name
        m = re.search(r'https?://(?:www\.)?([^/]+)', url)
        company = m.group(1) if m else url

    jobs: List[Dict[str, Any]] = []
    seen_titles: set = set()

    # --- Pass 1: headings (h2/h3/h4) ----------------------------------------
    for m in re.finditer(r'<h[234][^>]*>(.*?)</h[234]>', html, re.I | re.S):
        text = _html_to_text(m.group(1)).strip()
        if not _looks_like_job_title(text) or text.lower() in seen_titles:
            continue
        seen_titles.add(text.lower())
        # Grab the text that follows the heading (up to 800 chars) as description
        pos_end = m.end()
        snippet = _html_to_text(html[pos_end: pos_end + 1200])[:500]
        jobs.append(make_job(
            title=text,
            company=company,
            location="Tokyo, Japan",  # assume Tokyo unless text says otherwise
            url=url,
            description=snippet,
            source="company_site",
            skills=_extract_basic_skills(f"{text} {snippet}"),
        ))

    if jobs:
        return jobs

    # --- Pass 2: table cells <td> --------------------------------------------
    for m in re.finditer(r'<td[^>]*>(.*?)</td>', html, re.I | re.S):
        text = _html_to_text(m.group(1)).strip()
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
            skills=_extract_basic_skills(text),
        ))

    if jobs:
        return jobs

    # --- Pass 3: list items <li> ---------------------------------------------
    for m in re.finditer(r'<li[^>]*>(.*?)</li>', html, re.I | re.S):
        text = _html_to_text(m.group(1)).strip()
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
            skills=_extract_basic_skills(text),
        ))

    return jobs


def _extract_json_ld_jobpostings(html: str, base_url: str) -> List[Dict[str, Any]]:
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
                ))
    return jobs


def _extract_jobs_from_rendered_html(html: str, base_url: str, source_name: str = "unknown") -> List[Dict[str, Any]]:
    """Extract job listings from fully rendered HTML using all available strategies.

    Tries (in order): JSON-LD → Next.js __NEXT_DATA__ → Nuxt 3 __NUXT_DATA__ →
    Nuxt 2 window.__NUXT__ → generic application/json blobs.
    Returns on the first strategy that yields results.
    """
    if not html:
        return []

    # 1. JSON-LD structured data (most reliable when present)
    jobs = _extract_json_ld_jobpostings(html, base_url)
    if jobs:
        return jobs

    # 2. Next.js hydration blob
    for raw in re.findall(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, flags=re.I | re.S,
    ):
        try:
            jobs.extend(_scan_for_jobs(json.loads(raw.strip()), base_url, source_name))
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
            jobs.extend(_scan_for_jobs(json.loads(raw.strip()), base_url, source_name))
        except Exception:
            pass
    if jobs:
        return jobs

    # 4. Nuxt 2: window.__NUXT__ = {...};
    for m in re.finditer(r'window\.__NUXT__\s*=\s*(\{.*?\})\s*(?:;|</script>)', html, re.S):
        try:
            jobs.extend(_scan_for_jobs(json.loads(m.group(1)), base_url, source_name))
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
            jobs.extend(_scan_for_jobs(json.loads(raw.strip()), base_url, source_name))
        except Exception:
            pass

    return jobs


def fetch_browser_site(url: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    """Fetch a careers page using headless Playwright — handles React/Vue/Next.js/Nuxt SPAs.

    Use this provider (``"browser_site"``) for any source whose static HTML is empty
    because the page is client-side rendered.  Falls back to a descriptive warning
    when Playwright is not installed so the rest of the pipeline is unaffected.
    """
    provider = "browser_site"
    fetch_options = fetch_options or {}
    timeout_ms = int(
        fetch_options.get("browser_timeout_seconds",
                          fetch_options.get("timeout_seconds", 30)) * 1000
    )
    wait_until = fetch_options.get("browser_wait_until", "networkidle")

    html, issues = _playwright_get_text(url, timeout_ms=timeout_ms, wait_until=wait_until)
    result = FetchResult(provider=provider, issues=issues)

    if not html:
        return result

    jobs = _extract_jobs_from_rendered_html(html, url, provider)

    if not jobs:
        # Follow career/recruit links found in the rendered page
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
        candidate_links: List[str] = []
        keywords = ("job", "jobs", "career", "careers", "recruit", "position",
                    "opening", "採用", "求人", "キャリア")
        for href in hrefs:
            if any(k in href.lower() for k in keywords):
                full = urljoin(url, href)
                if full != url and full not in candidate_links:
                    candidate_links.append(full)

        max_follow = fetch_options.get("max_follow_links", 3)
        for link in candidate_links[:max_follow]:
            child_html, child_issues = _playwright_get_text(
                link, timeout_ms=timeout_ms, wait_until=wait_until,
            )
            result.issues.extend(child_issues)
            if child_html:
                jobs.extend(_extract_jobs_from_rendered_html(child_html, link, provider))

    if not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message=(
                "Browser rendered the page but found no structured job data. "
                "The site may use a fully custom listing format or require login."
            ),
            severity="warning",
            retryable=False,
        ))

    result.jobs = jobs
    return result


def fetch_company_site(url: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    provider = "company_site"
    fetch_options = fetch_options or {}
    timeout = fetch_options.get("timeout_seconds", 15)
    retries = fetch_options.get("max_retries", 1)
    backoff = fetch_options.get("retry_backoff_seconds", 0.5)

    html, issues = _safe_get_text(url, provider=provider,
                                   timeout_seconds=timeout, max_retries=retries,
                                   retry_backoff_seconds=backoff)
    result = FetchResult(provider=provider, issues=issues)
    if not html:
        return result

    # 1. JSON-LD structured data (best quality)
    jobs = _extract_json_ld_jobpostings(html, url)
    if jobs:
        result.jobs = jobs
        return result

    # 2. Follow career/recruit links (Japanese: 採用, 求人; English: career/jobs)
    career_keywords = ("job", "jobs", "career", "careers", "recruit", "position",
                       "opening", "採用", "求人", "キャリア", "saiyou")
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    candidate_links: List[str] = []
    for href in hrefs:
        if any(k in href.lower() for k in career_keywords):
            full = urljoin(url, href)
            if full != url and full not in candidate_links:
                candidate_links.append(full)

    followed_htmls: List[tuple[str, str]] = []
    max_follow_links = fetch_options.get("max_follow_links", 3)
    for link in candidate_links[:max_follow_links]:
        child_html, child_issues = _safe_get_text(link, provider=provider,
                                                   timeout_seconds=timeout,
                                                   max_retries=retries,
                                                   retry_backoff_seconds=backoff)
        result.issues.extend(child_issues)
        if not child_html:
            continue
        followed_htmls.append((child_html, link))
        child_jobs = _extract_json_ld_jobpostings(child_html, link)
        jobs.extend(child_jobs)

    if jobs:
        result.jobs = jobs
        return result

    # 3. Heuristic extraction — plain HTML tables/lists (Japanese career pages)
    jobs = _extract_jobs_from_html_heuristic(html, url)
    if not jobs:
        for child_html, child_url in followed_htmls:
            jobs = _extract_jobs_from_html_heuristic(child_html, child_url)
            if jobs:
                break

    if not followed_htmls and not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="No career links found and heuristic extraction yielded nothing",
            severity="warning",
            retryable=False,
        ))
    elif not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="Careers page found but no jobs extracted (JSON-LD or heuristic)",
            severity="warning",
            retryable=False,
            details={"followed_links": len(followed_htmls)},
        ))

    result.jobs = jobs
    return result


def _scan_for_jobs(data: Any, source_url: str, source_name: str = "unknown") -> List[Dict[str, Any]]:
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
                jobs.extend(_scan_for_jobs(v, source_url, source_name))
    elif isinstance(data, list):
        for item in data:
            jobs.extend(_scan_for_jobs(item, source_url, source_name))
    return jobs


def _spa_fetch_with_browser_fallback(
    url: str,
    provider: str,
    fetch_options: Dict[str, Any],
    spa_hint: str = "",
) -> FetchResult:
    """Shared helper: static fetch → extract → browser fallback if empty.

    1. Fetch static HTML via requests.
    2. Run _extract_jobs_from_rendered_html (covers JSON-LD, Next/Nuxt blobs, etc.).
    3. If still empty and Playwright is available, retry with headless browser.
    """
    timeout = fetch_options.get("timeout_seconds", 15)
    retries = fetch_options.get("max_retries", 1)
    backoff = fetch_options.get("retry_backoff_seconds", 0.5)

    html, issues = _safe_get_text(
        url, provider=provider,
        timeout_seconds=timeout, max_retries=retries, retry_backoff_seconds=backoff,
    )
    result = FetchResult(provider=provider, issues=issues)

    jobs: List[Dict[str, Any]] = []
    if html:
        jobs = _extract_jobs_from_rendered_html(html, url, provider)

    if not jobs:
        # Attempt headless browser fallback
        timeout_ms = int(fetch_options.get("browser_timeout_seconds", 30) * 1000)
        wait_until = fetch_options.get("browser_wait_until", "networkidle")
        browser_html, browser_issues = _playwright_get_text(
            url, timeout_ms=timeout_ms, wait_until=wait_until,
        )
        # Only surface Playwright issues when the static fetch also yielded nothing
        result.issues.extend(browser_issues)
        if browser_html:
            jobs = _extract_jobs_from_rendered_html(browser_html, url, provider)

    if not jobs:
        hint = f" ({spa_hint})" if spa_hint else ""
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message=(
                f"{provider}{hint}: no job data found in static HTML or browser render. "
                "The site may be fully JS-rendered with Algolia/custom APIs — "
                "consider adding it as a 'browser_site' source with specific subpages."
            ),
            severity="warning",
            retryable=False,
        ))

    result.jobs = jobs
    return result


def fetch_japan_dev(fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    """Fetch jobs from japan-dev.com (Nuxt/Algolia SPA).

    The rendered HTML contains job titles in <h2><a class="job-item__title">
    and company names in a parent element's data attribute.  We parse these
    directly from the rendered DOM rather than looking for JSON blobs.
    """
    fetch_options = fetch_options or {}
    provider = "japan_dev"
    base_url = "https://japan-dev.com"
    jobs_url = f"{base_url}/jobs"

    timeout_ms = int(fetch_options.get("browser_timeout_seconds", 30) * 1000)
    wait_until = fetch_options.get("browser_wait_until", "domcontentloaded")

    html, issues = _playwright_get_text(jobs_url, timeout_ms=timeout_ms, wait_until=wait_until)
    result = FetchResult(provider=provider, issues=issues)

    if not html:
        return result

    jobs: List[Dict[str, Any]] = []

    # Pattern: <h2><a href="/jobs/{company}/{slug}" class="job-item__title">TITLE</a></h2>
    # Company name sits in a parent element: data-...="COMPANY"  or in .job-item__contract-type
    for m in re.finditer(
        r'<h2[^>]*>\s*<a\s+href=["\'](/jobs/([^/"\']+)/[^"\']+)["\'][^>]*class=["\'][^"\']*job-item__title[^"\']*["\'][^>]*>(.*?)</a>\s*</h2>',
        html, re.I | re.S,
    ):
        href, company_slug, raw_title = m.group(1), m.group(2), m.group(3)
        title = unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        company = company_slug.replace("-", " ").title()

        # Grab nearby text for description (up to 400 chars after the heading)
        pos = m.end()
        nearby = unescape(re.sub(r"<[^>]+>", " ", html[pos: pos + 600])).strip()[:300]

        jobs.append(make_job(
            title=title,
            company=company,
            location="Japan (Tokyo / Remote)",
            url=f"{base_url}{href}",
            description=nearby,
            source=provider,
            skills=_extract_basic_skills(f"{title} {nearby}"),
        ))

    if jobs:
        result.jobs = jobs
        return result

    # Fallback: generic SPA extraction
    return _spa_fetch_with_browser_fallback(
        jobs_url, provider=provider, fetch_options=fetch_options,
        spa_hint="Nuxt/Algolia SPA",
    )


def fetch_gaijinpot(fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    """Fetch jobs from GaijinPot Jobs (jobs.gaijinpot.com).

    GaijinPot targets foreign workers in Japan with JLPT N2/N3 roles —
    a strong source for Chinese speakers in transition.
    Attempts static extraction first, then headless browser fallback.
    """
    fetch_options = fetch_options or {}
    provider = "gaijinpot"
    base_url = "https://jobs.gaijinpot.com"

    # Try the JSON search endpoint first (occasionally returns structured data)
    data, issues = _safe_get_json(
        f"{base_url}/job/index/search",
        provider=provider,
        timeout_seconds=fetch_options.get("timeout_seconds", 15),
        max_retries=fetch_options.get("max_retries", 1),
        retry_backoff_seconds=fetch_options.get("retry_backoff_seconds", 0.5),
    )
    if data:
        jobs = _scan_for_jobs(data, base_url, provider)
        if jobs:
            return FetchResult(provider=provider, jobs=jobs, issues=issues)

    return _spa_fetch_with_browser_fallback(
        base_url,
        provider=provider,
        fetch_options=fetch_options,
        spa_hint="Django + client-side JS",
    )


def fetch_tokyodev(fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    """Fetch jobs from TokyoDev (tokyodev.com/jobs).

    TokyoDev is a Rails application.  Job listings are embedded as
    /companies/{company-slug}/jobs/{job-slug} hrefs in the rendered HTML, so
    we extract them directly from those URL slugs — no JSON blob required.
    Falls back to _spa_fetch_with_browser_fallback if the slug approach yields
    nothing (e.g. the site structure changes in the future).
    """
    fetch_options = fetch_options or {}
    provider = "tokyodev"
    base_url = "https://www.tokyodev.com"
    jobs_url = f"{base_url}/jobs"

    timeout_ms = int(fetch_options.get("browser_timeout_seconds", 30) * 1000)
    wait_until = fetch_options.get("browser_wait_until", "domcontentloaded")

    html, issues = _playwright_get_text(jobs_url, timeout_ms=timeout_ms, wait_until=wait_until)
    result = FetchResult(provider=provider, issues=issues)

    if not html:
        return result

    # Extract jobs from /companies/{company-slug}/jobs/{job-slug} hrefs
    seen: set = set()
    jobs: List[Dict[str, Any]] = []
    for href, company_slug, job_slug in re.findall(
        r'href=["\'](/companies/([^/"\']+)/jobs/([^/"\'#?]+))["\']',
        html, re.I,
    ):
        key = (company_slug, job_slug)
        if key in seen:
            continue
        seen.add(key)
        company = company_slug.replace("-", " ").title()
        title   = job_slug.replace("-", " ").title()
        # Build full URL for the job detail page
        job_url = f"{base_url}{href}"
        # Infer description from title slug keywords + common context
        desc = f"{title} at {company}. English-friendly role in Tokyo, Japan."
        jobs.append(make_job(
            title=title,
            company=company,
            location="Tokyo, Japan",
            url=job_url,
            description=desc,
            source=provider,
            skills=_extract_basic_skills(f"{title} {desc}"),
        ))

    if jobs:
        result.jobs = jobs
        return result

    # Fallback: generic SPA extraction
    return _spa_fetch_with_browser_fallback(
        jobs_url,
        provider=provider,
        fetch_options=fetch_options,
        spa_hint="Rails/Hotwire SPA",
    )


def fetch_from_source(source: Dict[str, Any], fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    provider = source.get("provider")
    filters = source.get("filters")

    if provider == "greenhouse":
        result = fetch_greenhouse(source["token"], fetch_options=fetch_options)
    elif provider == "lever":
        result = fetch_lever(source["company"], fetch_options=fetch_options)
    elif provider == "ashby":
        result = fetch_ashby(source["board"], fetch_options=fetch_options)
    elif provider == "company_site":
        result = fetch_company_site(source["url"], fetch_options=fetch_options)
    elif provider == "browser_site":
        result = fetch_browser_site(source["url"], fetch_options=fetch_options)
    elif provider == "japan_dev":
        result = fetch_japan_dev(fetch_options=fetch_options)
    elif provider == "gaijinpot":
        result = fetch_gaijinpot(fetch_options=fetch_options)
    elif provider == "tokyodev":
        result = fetch_tokyodev(fetch_options=fetch_options)
    else:
        return FetchResult(
            provider=str(provider or "unknown"),
            issues=[
                FetchIssue(
                    provider=str(provider or "unknown"),
                    message="Unsupported provider in source config",
                    severity="error",
                    retryable=False,
                    details={"source": source},
                )
            ],
        )

    filtered_jobs, filter_issues = _apply_source_filters(result.jobs, filters, provider=str(provider))
    result.jobs = filtered_jobs
    result.issues.extend(filter_issues)
    return result


def fetch_all(sources: Iterable[Dict[str, Any]], fetch_options: Dict[str, Any] | None = None) -> Dict[str, Any]:
    fetch_options = fetch_options or {}

    active_sources: List[Dict[str, Any]] = []
    for source in sources:
        if isinstance(source, dict) and source and all(k.startswith("_") for k in source.keys()):
            continue
        active_sources.append(source)

    if not active_sources:
        return {"jobs": [], "issues": []}

    all_jobs: List[Dict[str, Any]] = []
    all_issues: List[Dict[str, Any]] = []

    max_workers = fetch_options.get("max_concurrent_fetches")
    if not isinstance(max_workers, int) or max_workers <= 0:
        max_workers = min(4, len(active_sources)) or 1

    def _collect(result: FetchResult) -> None:
        all_jobs.extend(result.jobs)
        all_issues.extend([
            {
                "provider": issue.provider,
                "message": issue.message,
                "source_ref": issue.source_ref,
                "severity": issue.severity,
                "retryable": issue.retryable,
                "details": issue.details,
            }
            for issue in result.issues
        ])

    def _safe_fetch(source: Dict[str, Any]) -> FetchResult:
        try:
            return fetch_from_source(source, fetch_options=fetch_options)
        except Exception as exc:  # noqa: BLE001
            provider = "unknown"
            if isinstance(source, dict):
                provider = str(source.get("provider") or "unknown")
            return FetchResult(
                provider=provider,
                issues=[
                    FetchIssue(
                        provider=provider,
                        message=f"未处理的抓取异常：{exc}",
                        severity="error",
                        retryable=False,
                        details={"source": source},
                    )
                ],
            )

    if max_workers == 1:
        for source in active_sources:
            _collect(_safe_fetch(source))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_safe_fetch, source): source for source in active_sources}
            for future in as_completed(future_map):
                _collect(future.result())

    return {
        "jobs": all_jobs,
        "issues": all_issues,
    }


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
