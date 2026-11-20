"""增量缓存测试。"""

import json
from datetime import datetime, timedelta

import pytest

from xdfvafinder.cache import InvalidCache


def _cache(path, ttl_days: float = 30.0) -> InvalidCache:
    return InvalidCache(path, ttl_days=ttl_days)


def _write_cache(path, entries: dict[int, int]) -> None:
    """entries: {digits: 距今天数}。"""

    def stamp_of(days: int) -> str:
        return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")

    path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": stamp_of(0),
                "invalid": {str(d): stamp_of(days) for d, days in entries.items()},
            }
        ),
        encoding="utf-8",
    )


class TestLoadSave:
    def test_roundtrip(self, tmp_path):
        path = tmp_path / "scan_cache.json"
        cache = _cache(path)
        cache.mark_invalid(1)
        cache.mark_invalid(2)
        cache.save()

        loaded = _cache(path)
        assert loaded.load() == 2
        assert loaded.is_invalid(1)
        assert loaded.is_invalid(2)
        assert not loaded.is_invalid(3)

    def test_file_format(self, tmp_path):
        path = tmp_path / "scan_cache.json"
        cache = _cache(path)
        cache.mark_invalid(12345)
        cache.save()

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert set(data["invalid"]) == {"12345"}
        assert "updated_at" in data
        assert not (tmp_path / "scan_cache.json.tmp").exists()

    def test_missing_file(self, tmp_path):
        assert _cache(tmp_path / "nope.json").load() == 0

    @pytest.mark.parametrize(
        "content",
        [
            "",
            "{",
            "[]",
            "{}",
            '{"invalid": []}',
            '{"invalid": {"abc": "2026-01-01T00:00:00"}}',
            '{"invalid": {"7": "not-a-time"}}',
        ],
    )
    def test_corrupt_file_ignored(self, tmp_path, content):
        path = tmp_path / "scan_cache.json"
        path.write_text(content, encoding="utf-8")
        assert _cache(path).load() == 0


class TestTtl:
    def test_expired_entries_are_dropped_on_load(self, tmp_path):
        path = tmp_path / "scan_cache.json"
        _write_cache(path, {7: 10})
        assert _cache(path, ttl_days=5).load() == 0

    def test_fresh_entries_are_kept(self, tmp_path):
        path = tmp_path / "scan_cache.json"
        _write_cache(path, {7: 1})
        cache = _cache(path, ttl_days=5)
        assert cache.load() == 1
        assert cache.is_invalid(7)

    def test_zero_ttl_never_expires(self, tmp_path):
        path = tmp_path / "scan_cache.json"
        path.write_text(
            json.dumps({"version": 1, "invalid": {"7": "2000-01-01T00:00:00"}}),
            encoding="utf-8",
        )
        cache = _cache(path, ttl_days=0)
        assert cache.load() == 1
        assert cache.is_invalid(7)
        assert cache.ttl_days is None

    def test_prune_removes_only_expired(self, tmp_path):
        cache = _cache(tmp_path / "scan_cache.json", ttl_days=1)
        cache.mark_invalid(1, now=datetime.now() - timedelta(days=2))
        cache.mark_invalid(2)

        assert cache.prune() == 1
        assert not cache.is_invalid(1)
        assert cache.is_invalid(2)
        assert len(cache) == 1
