import json

import pytest

from job_finder.config import (
    DEFAULT_FETCH_OPTIONS,
    load_config,
    load_priority_companies,
    validate_config,
)


def _write(tmp_path, data, name="sources.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


class TestLoadConfig:
    def test_fills_defaults(self, tmp_path):
        cfg = load_config(_write(tmp_path, {}))
        assert cfg["sources"] == []
        assert cfg["fetch_options"] == DEFAULT_FETCH_OPTIONS

    def test_user_fetch_options_override_defaults(self, tmp_path):
        cfg = load_config(_write(tmp_path, {"fetch_options": {"timeout_seconds": 3}}))
        assert cfg["fetch_options"]["timeout_seconds"] == 3
        assert cfg["fetch_options"]["max_retries"] == DEFAULT_FETCH_OPTIONS["max_retries"]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(str(tmp_path / "nope.json"))

    def test_invalid_json_raises_with_path(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{oops", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError, match="bad.json"):
            load_config(str(p))


def test_load_priority_companies_missing_file_returns_empty(tmp_path):
    cfg = load_priority_companies(str(tmp_path / "none.json"))
    assert cfg["named_companies"] == []


def test_load_priority_companies_reads_file(tmp_path):
    path = _write(tmp_path, {"named_companies": [{"name": "X"}]})
    assert load_priority_companies(path)["named_companies"][0]["name"] == "X"


class TestValidateConfig:
    def _cfg(self, sources, **extra):
        return {"sources": sources, "fetch_options": dict(DEFAULT_FETCH_OPTIONS), **extra}

    def test_valid_config(self):
        errors, warnings = validate_config(self._cfg([{"provider": "greenhouse", "token": "t"}]))
        assert errors == [] and warnings == []

    def test_sources_must_be_list(self):
        errors, _ = validate_config({"sources": {}})
        assert errors

    def test_unknown_provider(self):
        errors, _ = validate_config(self._cfg([{"provider": "nope"}]))
        assert any("不支持" in e for e in errors)

    def test_missing_required_field(self):
        errors, _ = validate_config(self._cfg([{"provider": "lever"}]))
        assert any("company" in e for e in errors)

    def test_separator_objects_skipped(self):
        errors, warnings = validate_config(self._cfg([{"_comment": "x"}, {"provider": "japan_dev"}]))
        assert errors == [] and warnings == []

    def test_unknown_source_field_warns(self):
        _, warnings = validate_config(self._cfg([{"provider": "japan_dev", "extra": 1}]))
        assert any("extra" in w for w in warnings)

    def test_filter_validation(self):
        bad = {"provider": "japan_dev", "filters": {"keywords": [""], "remote_only": "yes", "weird": 1}}
        errors, warnings = validate_config(self._cfg([bad]))
        assert len(errors) == 2 and len(warnings) == 1

    def test_filters_must_be_object(self):
        errors, _ = validate_config(self._cfg([{"provider": "japan_dev", "filters": []}]))
        assert errors

    def test_bad_fetch_options(self):
        cfg = self._cfg([], fetch_options={"timeout_seconds": 0, "max_retries": -1,
                                           "retry_backoff_seconds": -1, "max_follow_links": -1,
                                           "browser_timeout_seconds": 0, "max_concurrent_fetches": 0})
        errors, _ = validate_config(cfg)
        assert len(errors) == 6

    def test_empty_sources_warns(self):
        _, warnings = validate_config(self._cfg([]))
        assert warnings

    def test_example_config_is_valid(self):
        cfg = load_config("config/sources.example.json")
        errors, _ = validate_config(cfg)
        assert errors == []


class TestProviderRegistryIsSingleSourceOfTruth:
    def test_supported_providers_derive_from_registry(self):
        from job_finder.config import SUPPORTED_PROVIDERS
        from job_finder.providers import PROVIDERS

        assert set(SUPPORTED_PROVIDERS) == set(PROVIDERS)
        assert all(SUPPORTED_PROVIDERS[n] == list(p.required) for n, p in PROVIDERS.items())

    def test_known_required_fields_unchanged(self):
        from job_finder.config import SUPPORTED_PROVIDERS

        assert SUPPORTED_PROVIDERS["greenhouse"] == ["token"]
        assert SUPPORTED_PROVIDERS["lever"] == ["company"]
        assert SUPPORTED_PROVIDERS["browser_site"] == ["url"]
        assert SUPPORTED_PROVIDERS["tokyodev"] == []


class TestEnabledFlag:
    def _validate(self, source):
        return validate_config({"sources": [source], "fetch_options": dict(DEFAULT_FETCH_OPTIONS)})

    def test_enabled_false_is_accepted_without_warning(self):
        errors, warnings = self._validate({"provider": "japan_dev", "enabled": False})
        assert errors == [] and warnings == []

    def test_enabled_must_be_boolean(self):
        errors, _ = self._validate({"provider": "japan_dev", "enabled": "no"})
        assert any("enabled" in e for e in errors)
