import pytest

from job_finder.providers.text import extract_basic_skills, html_to_text, job_text


class TestExtractBasicSkills:
    def test_finds_listed_skills(self):
        assert extract_basic_skills("We use Python, Docker and PostgreSQL.") == ["Python", "Docker", "PostgreSQL"]

    @pytest.mark.parametrize("text,absent", [
        ("average storage leverage", "RAG"),
        ("project management and engagement", "Agent"),
        ("we are going to grow, good ago", "Go"),
        ("JavaScript only", "Java"),
        ("Gen2 and Spring3", "N2"),
        ("Hudson and Orange", "Go"),
    ])
    def test_does_not_match_inside_other_words(self, text, absent):
        assert absent not in extract_basic_skills(text)

    @pytest.mark.parametrize("text,present", [
        ("Built a RAG pipeline", "RAG"),
        ("Go and Rust", "Go"),
        ("C# and .NET Core", "C#"),
        ("ASP.NET services", ".NET"),
        ("JLPT N2 required", "N2"),
        ("日本語と英語が必要", "日本語"),
        ("Experience with AI agents", "Agent"),
    ])
    def test_still_matches_real_mentions(self, text, present):
        assert present in extract_basic_skills(text)

    def test_empty_and_none(self):
        assert extract_basic_skills("") == [] and extract_basic_skills(None) == []  # type: ignore[arg-type]


def test_html_to_text_strips_tags_and_entities():
    assert html_to_text("<p>R&amp;D   <b>team</b></p>") == "R&D team"
    assert html_to_text(None) == ""  # type: ignore[arg-type]


def test_job_text_is_lowercased_and_joins_fields():
    text = job_text({"title": "Dev", "company": "ACME", "location": "Tokyo", "description": "X", "skills": ["Go"]})
    assert text == "dev acme tokyo x go"
