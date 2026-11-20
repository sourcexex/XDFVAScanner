"""结果文件写入测试。"""

import pytest

from xdflib.models import StudentProfile
from xdfvafinder.storage import HEADER_FORMAT, ResultWriter


def _student(**overrides) -> StudentProfile:
    data = {
        "student_id": "s1",
        "student_code": "c1",
        "real_name": "张三",
        "grade_name": "初一",
        "school_id": "9",
        "school_name": "XDF 学校",
    }
    data.update(overrides)
    return StudentProfile(**data)


class TestResultWriter:
    def test_writes_header_and_student_rows(self, tmp_path):
        path = tmp_path / "valid_accounts.txt"
        writer = ResultWriter(path)
        writer.open(start=0, end=9, truncate=True)
        writer.write_valid("14400000444", "XdFopt00000", "u2-1", [_student()])
        writer.close()

        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# XDF 账号扫描结果 (")
        assert lines[1] == "# 范围: 00000 ~ 00009"
        assert lines[2] == f"# 格式: {HEADER_FORMAT}"
        assert lines[3] == "#"
        assert lines[4] == "14400000444|XdFopt00000|u2-1|s1|c1|张三|初一|9|XDF 学校"

    def test_one_row_per_student(self, tmp_path):
        path = tmp_path / "valid_accounts.txt"
        writer = ResultWriter(path)
        writer.open(start=0, end=0, truncate=True)
        writer.write_valid(
            "14400000444",
            "XdFopt00000",
            "u2-1",
            [_student(student_id="s1"), _student(student_id="s2", real_name="李四")],
        )
        writer.close()

        rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line[0] != "#"]
        assert len(rows) == 2
        assert rows[1].split("|")[3] == "s2"

    def test_empty_students_keeps_nine_columns(self, tmp_path):
        path = tmp_path / "valid_accounts.txt"
        writer = ResultWriter(path)
        writer.open(start=0, end=0, truncate=True)
        writer.write_valid("14400000444", "XdFopt00000", "u2-1", [])
        writer.close()

        row = path.read_text(encoding="utf-8").splitlines()[4]
        assert row == "14400000444|XdFopt00000|u2-1||||||"
        assert len(row.split("|")) == len(HEADER_FORMAT.split("|")) == 9

    def test_append_mode_keeps_previous_content(self, tmp_path):
        path = tmp_path / "valid_accounts.txt"
        path.write_text("old\n", encoding="utf-8")
        writer = ResultWriter(path)
        writer.open(start=0, end=1, truncate=False)
        writer.write_valid("m", "p", "u", [])
        writer.close()

        assert path.read_text(encoding="utf-8") == "old\nm|p|u||||||\n"

    def test_close_is_idempotent(self, tmp_path):
        writer = ResultWriter(tmp_path / "valid_accounts.txt")
        writer.open(start=0, end=0, truncate=True)
        writer.close()
        writer.close()

    def test_write_before_open_raises(self, tmp_path):
        writer = ResultWriter(tmp_path / "valid_accounts.txt")
        with pytest.raises(RuntimeError, match=r"open\(\)"):
            writer.write_valid("m", "p", "u", [])
