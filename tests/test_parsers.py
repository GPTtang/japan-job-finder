from job_finder.parsers import parse_user_query


def test_extracts_roles_skills_and_locations():
    p = parse_user_query("Backend Engineer in Tokyo, Python and FastAPI")
    assert "Backend Engineer" in p["target_roles"]
    assert {"Python", "FastAPI"} <= set(p["skills"])
    assert {"Tokyo", "東京", "东京"} <= set(p["locations"])


def test_location_aliases_expand_to_all_forms():
    assert {"Osaka", "大阪"} <= set(parse_user_query("大阪で働きたい")["locations"])


def test_remote_preference_levels():
    assert parse_user_query("fully remote")["remote_preference"] == "only"
    assert parse_user_query("remote ok")["remote_preference"] == "prefer"
    assert parse_user_query("onsite")["remote_preference"] is None


def test_jlpt_picks_highest_declared_level():
    assert parse_user_query("jlpt n2 holder, studying jlpt n1")["jlpt_level"] == "N1"


def test_jlpt_absent():
    assert parse_user_query("no japanese")["jlpt_level"] is None


def test_chinese_speaker_flag():
    assert parse_user_query("I am a native chinese engineer")["is_chinese_speaker"]
    assert not parse_user_query("I speak english")["is_chinese_speaker"]


def test_raw_query_is_stripped():
    assert parse_user_query("  hello  ")["raw_query"] == "hello"


def test_go_skill_not_matched_inside_other_words():
    assert "Go" not in parse_user_query("I am good at Python, going places")["skills"]
    assert "Go" in parse_user_query("Python and Go developer")["skills"]


def test_java_not_matched_inside_javascript():
    assert "Java" not in parse_user_query("JavaScript developer")["skills"]


def test_symbol_skills_still_match():
    skills = parse_user_query("C# and .NET with ASP.NET experience")["skills"]
    assert "C#" in skills and ".NET" in skills


def test_jlpt_level_not_matched_inside_other_words():
    assert parse_user_query("Gen2 hardware")["jlpt_level"] is None
