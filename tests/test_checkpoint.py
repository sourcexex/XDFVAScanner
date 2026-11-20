"""断点读写与连续水位测试。"""

import json

import pytest

from xdfvafinder.checkpoint import ProgressTracker, ScanState, read_state, write_state


def _state(**overrides) -> ScanState:
    data = {
        "last_digits": 42,
        "end": 99,
        "env": "test",
        "valid_count": 3,
        "total_scanned": 43,
        "updated_at": "2026-01-01T00:00:00",
    }
    data.update(overrides)
    return ScanState(**data)


class TestScanState:
    def test_roundtrip(self, tmp_path):
        path = tmp_path / "scan_progress.json"
        state = _state()
        write_state(path, state)
        assert read_state(path) == state

    def test_file_format_matches_legacy(self, tmp_path):
        path = tmp_path / "scan_progress.json"
        write_state(path, _state())
        assert json.loads(path.read_text(encoding="utf-8")) == {
            "last_digits": 42,
            "end": 99,
            "env": "test",
            "valid_count": 3,
            "total_scanned": 43,
            "updated_at": "2026-01-01T00:00:00",
        }

    def test_write_is_atomic(self, tmp_path):
        path = tmp_path / "scan_progress.json"
        write_state(path, _state())
        assert not (tmp_path / "scan_progress.json.tmp").exists()

    def test_missing_file(self, tmp_path):
        assert read_state(tmp_path / "nope.json") is None

    @pytest.mark.parametrize(
        "content",
        ["", "{", "[]", "{}", '{"last_digits": "7"}', '{"last_digits": true}'],
    )
    def test_corrupt_file_is_ignored(self, tmp_path, content):
        path = tmp_path / "scan_progress.json"
        path.write_text(content, encoding="utf-8")
        assert read_state(path) is None


class TestProgressTracker:
    def test_nothing_marked(self):
        assert ProgressTracker(5).last_contiguous is None

    def test_advances_only_when_contiguous(self):
        tracker = ProgressTracker(10)
        assert tracker.mark(11) is None
        assert tracker.mark(12) is None
        assert tracker.mark(10) == 12
        assert tracker.last_contiguous == 12

    def test_advances_one_by_one(self):
        tracker = ProgressTracker(0)
        assert tracker.mark(0) == 0
        assert tracker.mark(1) == 1
        assert tracker.last_contiguous == 1

    def test_duplicate_marks_are_idempotent(self):
        tracker = ProgressTracker(0)
        assert tracker.mark(0) == 0
        assert tracker.mark(0) == 0
        assert tracker.last_contiguous == 0

    def test_marked_set_is_bounded(self):
        """已推进的号码不应继续占用内存。"""
        tracker = ProgressTracker(0)
        for digits in range(1000):
            tracker.mark(digits)
        assert tracker.last_contiguous == 999
        assert tracker._done == set()  # 内部状态：已推进的号码不再占用内存
