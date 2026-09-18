from muc_notice_engine.core.sources import PORTAL_TYPES, SOURCES, resolve_source


def test_source_count():
    assert len(SOURCES) == 32
    assert len(PORTAL_TYPES) == 11


def test_public_source_count():
    assert len([s for s in SOURCES if not s.get("requires_auth", False)]) == 21


def test_portal_types_cover_all_valid():
    assert set(PORTAL_TYPES) == {1, 3, 4, 5, 6, 8, 9, 10, 11, 32, 36}


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
