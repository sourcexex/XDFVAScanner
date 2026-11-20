"""增量扫描缓存：记录"上次确认不可用"的号码，下次扫描直接跳过。

只缓存**明确被拒绝**的账号（登录接口正常返回、判定为不可用）。网络错误、任务异常
和中断都不会写入缓存——这些不是账号本身的状态，下次应该重试。

条目带时间戳，超过 TTL 的会被重新检查，避免永久跳过后来可能开通的账号。
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

CACHE_FILE = "scan_cache.json"
CACHE_VERSION = 1
DEFAULT_TTL_DAYS = 30.0

logger = logging.getLogger("scanner.cache")

__all__ = ["CACHE_FILE", "CACHE_VERSION", "DEFAULT_TTL_DAYS", "InvalidCache"]


def _parse_time(value: object) -> datetime | None:
    """解析缓存里的时间戳；非法值返回 ``None``（该条会被丢弃/重查）。"""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class InvalidCache:
    """不可用账号缓存。

    文件格式（``scan_cache.json``）::

        {
          "version": 1,
          "updated_at": "2026-11-20T20:00:00",
          "invalid": {"12345": "2026-11-20T19:00:00", ...}
        }
    """

    def __init__(
        self,
        path: str | Path = CACHE_FILE,
        *,
        ttl_days: float = DEFAULT_TTL_DAYS,
    ) -> None:
        self.path = Path(path)
        self.ttl = timedelta(days=ttl_days) if ttl_days > 0 else None
        self._entries: dict[int, datetime] = {}

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def ttl_days(self) -> float | None:
        """有效期（天）；``None`` 表示永不过期。"""
        return None if self.ttl is None else self.ttl.total_seconds() / 86400

    def load(self) -> int:
        """读取缓存并丢弃过期/非法条目；返回剩余条目数。"""
        if not self.path.exists():
            return 0

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("增量缓存损坏，忽略: %s", exc)
            return 0

        if not isinstance(data, dict):
            logger.warning("增量缓存损坏，忽略: 顶层不是 JSON 对象")
            return 0

        raw = data.get("invalid")
        if not isinstance(raw, dict):
            return 0

        now = datetime.now()
        dropped = 0
        for key, value in raw.items():
            try:
                digits = int(key)
            except (TypeError, ValueError):
                dropped += 1
                continue
            checked_at = _parse_time(value)
            if checked_at is None or self._expired(checked_at, now):
                dropped += 1
                continue
            self._entries[digits] = checked_at

        if dropped:
            logger.info("增量缓存中 %d 条已过期或非法，本次会重新检查", dropped)
        return len(self._entries)

    def is_invalid(self, digits: int, *, now: datetime | None = None) -> bool:
        """该号码是否在有效期内被确认过不可用（可跳过）。"""
        checked_at = self._entries.get(digits)
        if checked_at is None:
            return False
        return not self._expired(checked_at, now or datetime.now())

    def mark_invalid(self, digits: int, *, now: datetime | None = None) -> None:
        """记录一个"确认不可用"的号码。"""
        self._entries[digits] = now or datetime.now()

    def prune(self, *, now: datetime | None = None) -> int:
        """清掉过期条目，返回清理条数。"""
        now = now or datetime.now()
        expired = [digits for digits, when in self._entries.items() if self._expired(when, now)]
        for digits in expired:
            del self._entries[digits]
        return len(expired)

    def save(self) -> None:
        """原子写入缓存（先写 ``.tmp`` 再替换）。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CACHE_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "invalid": {
                str(digits): when.isoformat(timespec="seconds")
                for digits, when in sorted(self._entries.items())
            },
        }
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, self.path)

    def _expired(self, checked_at: datetime, now: datetime) -> bool:
        return self.ttl is not None and now - checked_at > self.ttl
