from muc_notice_engine.core.sources import SOURCES, resolve_source


def test_source_count():
    assert len(SOURCES) == 14


def test_source_keys_unique():
    keys = [s["key"] for s in SOURCES]
    assert len(keys) == len(set(keys))


def test_every_source_has_required_fields():
    for source in SOURCES:
        assert source["key"]
        assert source["name"]
        assert source["url"].startswith("http")
        assert source["selector"]


def test_resolve_source_by_key_and_name():
    assert resolve_source("muc_tzgg")["key"] == "muc_tzgg"
    assert resolve_source("研究生院 - 招生工作")["key"] == "grs_zs"


def test_resolve_unknown_returns_none():
    assert resolve_source("definitely-not-a-source") is None
