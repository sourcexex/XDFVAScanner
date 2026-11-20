"""扫描结果文件：表头 + 逐行追加（线程安全）。"""

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import TextIO

from xdflib.models import StudentProfile

logger = logging.getLogger("scanner.storage")

HEADER_FORMAT = "手机号|密码|u2_user_id|学员ID|学员编号|姓名|年级|学校ID|学校名"
COLUMN_COUNT = 9

__all__ = ["COLUMN_COUNT", "HEADER_FORMAT", "ResultWriter"]


class ResultWriter:
    """把有效账号按 ``手机号|密码|u2_user_id|...`` 逐行追加到结果文件。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._handle: TextIO | None = None

    def open(self, *, start: int, end: int, truncate: bool) -> None:
        """打开结果文件。

        参数:
            start:    本次扫描起始 digits（写入表头用）。
            end:      本次扫描结束 digits（写入表头用）。
            truncate: ``True`` 时清空文件并写入表头注释；``False`` 时续写。
        """
        with self._lock:
            if self._handle is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("w" if truncate else "a", encoding="utf-8")
            if truncate:
                self._write_header(self._handle, start=start, end=end)
            logger.debug("结果文件已打开: %s (truncate=%s)", self.path, truncate)

    @staticmethod
    def _write_header(handle: TextIO, *, start: int, end: int) -> None:
        handle.write(f"# XDF 账号扫描结果 ({datetime.now().isoformat()})\n")
        handle.write(f"# 范围: {start:05d} ~ {end:05d}\n")
        handle.write(f"# 格式: {HEADER_FORMAT}\n")
        handle.write("#\n")
        handle.flush()

    def write_valid(
        self,
        mobile: str,
        password: str,
        u2_user_id: str,
        students: list[StudentProfile],
    ) -> None:
        """写入一个有效账号；账号下没有学员时其余列留空。"""
        with self._lock:
            if self._handle is None:
                raise RuntimeError("结果文件尚未打开，请先调用 open()")
            if students:
                for student in students:
                    self._handle.write(_student_row(mobile, password, u2_user_id, student) + "\n")
            else:
                self._handle.write(_empty_students_row(mobile, password, u2_user_id) + "\n")
            self._handle.flush()

    def close(self) -> None:
        """关闭文件，可重复调用。"""
        with self._lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None


def _student_row(
    mobile: str,
    password: str,
    u2_user_id: str,
    student: StudentProfile,
) -> str:
    """拼一行 9 列的学员记录。"""
    return "|".join(
        [
            mobile,
            password,
            u2_user_id,
            student.student_id,
            student.student_code,
            student.real_name,
            student.grade_name,
            student.school_id,
            student.school_name,
        ]
    )


def _empty_students_row(mobile: str, password: str, u2_user_id: str) -> str:
    """拼一行 9 列的"无学员"记录，保持列数与表头一致。"""
    return "|".join([mobile, password, u2_user_id, *([""] * (COLUMN_COUNT - 3))])
