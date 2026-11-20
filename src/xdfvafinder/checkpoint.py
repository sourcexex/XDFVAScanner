"""扫描断点：状态读写与连续进度水位。

``scan_progress.json`` 记录"已经连续扫描到哪个 digits"。
只有连续区间的水位才会被保存，因此多线程乱序完成时也不会在 ``--resume`` 后漏扫号码。
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("scanner.checkpoint")

__all__ = ["ProgressTracker", "ScanState", "read_state", "write_state"]


@dataclass(frozen=True)
class ScanState:
    """``scan_progress.json`` 的内容。"""

    last_digits: int
    end: int
    env: str
    valid_count: int
    total_scanned: int
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        """转为可直接 ``json.dump`` 的字典（保持旧版字段名不变）。"""
        return {
            "last_digits": self.last_digits,
            "end": self.end,
            "env": self.env,
            "valid_count": self.valid_count,
            "total_scanned": self.total_scanned,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ScanState":
        """从 JSON 字典还原；``last_digits`` 无效时抛 ``ValueError``。"""
        last_digits = data.get("last_digits")
        if not isinstance(last_digits, int) or isinstance(last_digits, bool):
            raise ValueError(f"last_digits 缺失或不是整数: {last_digits!r}")
        return cls(
            last_digits=last_digits,
            end=_as_int(data.get("end"), -1),
            env=str(data.get("env", "")),
            valid_count=_as_int(data.get("valid_count"), 0),
            total_scanned=_as_int(data.get("total_scanned"), 0),
            updated_at=str(data.get("updated_at", "")),
        )


def _as_int(value: object, default: int) -> int:
    """宽松取整数：非整数（含 bool）时返回默认值。"""
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def read_state(path: str | Path) -> ScanState | None:
    """读取断点；文件不存在、损坏或字段无效时返回 ``None`` 并记录警告。"""
    file_path = Path(path)
    if not file_path.exists():
        return None

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("断点文件损坏，忽略: %s", exc)
        return None

    if not isinstance(data, dict):
        logger.warning("断点文件损坏，忽略: 顶层不是 JSON 对象")
        return None

    try:
        return ScanState.from_dict(data)
    except ValueError as exc:
        logger.warning("断点文件损坏，忽略: %s", exc)
        return None


def write_state(path: str | Path, state: ScanState) -> None:
    """原子写入断点：先写 ``.tmp`` 再 ``os.replace``，避免中断留下半个文件。"""
    file_path = Path(path)
    tmp_path = file_path.with_name(file_path.name + ".tmp")
    tmp_path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, file_path)


class ProgressTracker:
    """维护"从起点起连续扫描完成"的水位。

    多线程下号码是按完成顺序回报的，可能乱序。直接拿最后完成的号码当断点，
    会让 ``--resume`` 跳过仍然在途的低位号码；这里只在低位连续时才推进水位。
    """

    def __init__(self, first_digits: int) -> None:
        self._next = first_digits
        self._last: int | None = None
        self._done: set[int] = set()

    @property
    def last_contiguous(self) -> int | None:
        """已连续扫描到的最大 digits；一个都没扫完时返回 ``None``。"""
        return self._last

    def mark(self, digits: int) -> int | None:
        """标记某个号码已扫描完成，返回推进后的水位。"""
        self._done.add(digits)
        while self._next in self._done:
            self._done.discard(self._next)
            self._next += 1
            self._last = self._next - 1
        return self._last
