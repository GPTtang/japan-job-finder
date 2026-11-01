from job_finder.signals import has_any_term, has_term


def test_ascii_term_needs_word_boundary():
    assert has_term("jlpt n2 required", "n2")
    assert not has_term("gen2 hardware", "n2")
    assert not has_term("bridge security", "bridge se")


def test_ascii_term_matches_at_edges_and_punctuation():
    assert has_term("N2", "n2")
    assert has_term("(n1)", "n1")


def test_cjk_term_is_substring():
    assert has_term("中国語が話せる方", "中国語")


def test_symbol_edges_do_not_require_boundary():
    assert has_term("asp.net core", ".net")
    assert has_term("c# developer", "c#")


def test_has_any_term():
    assert has_any_term("offshore team", ["onsite", "offshore"])
    assert not has_any_term("nothing here", ["onsite", "offshore"])
