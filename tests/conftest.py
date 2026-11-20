"""pytest 公共夹具。"""

import logging

import pytest


@pytest.fixture(autouse=True)
def _close_scanner_log_handlers():
    """测试结束后关闭日志文件句柄，避免 Windows 上锁住 tmp_path。"""
    yield
    scanner_logger = logging.getLogger("scanner")
    for handler in list(scanner_logger.handlers):
        handler.close()
        scanner_logger.removeHandler(handler)
