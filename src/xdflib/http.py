"""带 XDF 签名头注入的 HTTP 客户端。"""

import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

import requests

from .config import XDFEnvConfig
from .crypto import build_signature_headers, generate_device_info
from .errors import XDFNetworkError

logger = logging.getLogger("xdflib.http")


class _RequestContext:
    """持有每个请求的一次性值（时间戳、guid、设备信息）。"""

    def __init__(self, env: XDFEnvConfig):
        self.timestamp = str(int(time.time() * 1000))
        self.device_info = generate_device_info()


def _is_retryable(error: Exception, status_code: int | None = None) -> bool:
    """判断错误是否值得重试。"""
    if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if status_code is not None and status_code >= 500:
        return True
    return False


# ================================================================
#  带 XDF 签名头的 POST / GET
# ================================================================


def _post_json(
    url: str,
    body: dict[str, Any],
    env: XDFEnvConfig,
    *,
    timeout: float = 15.0,
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    向 XDF API 发送带完整签名头的 JSON POST 请求。

    参数:
        url:          目标 URL。
        body:         JSON 请求体。
        env:          XDF 环境配置。
        timeout:      每次尝试的请求超时时间，以秒为单位。
        max_retries:  临时故障时的最大重试次数。

    返回:
        已解析的 JSON 响应体。

    抛出:
        XDFNetworkError: 所有重试耗尽时。
    """
    ctx = _RequestContext(env)
    parsed = urlparse(url)
    path_and_query = parsed.path + ("?" + parsed.query if parsed.query else "")
    headers = build_signature_headers(path_and_query, body, env, ctx.device_info)
    body_json = json.dumps(body, ensure_ascii=False, separators=(",", ":"))

    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, data=body_json, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout as e:
            last_exception = e
            logger.warning("POST %s 超时（第 %d/%d 次尝试）", url, attempt, max_retries)
        except requests.exceptions.ConnectionError as e:
            last_exception = e
            logger.warning("POST %s 连接错误（第 %d/%d 次尝试）", url, attempt, max_retries)
        except requests.exceptions.HTTPError as e:
            last_exception = e
            if e.response is not None and e.response.status_code >= 500:
                logger.warning("POST %s HTTP %d（第 %d/%d 次尝试）", url, e.response.status_code, attempt, max_retries)
            else:
                logger.error("POST %s HTTP %d: %s", url, e.response.status_code if e.response else 0, e)
                break
        except (requests.exceptions.JSONDecodeError, json.JSONDecodeError) as e:
            last_exception = e
            logger.error("POST %s 返回非 JSON 响应", url)
            break
        except requests.exceptions.RequestException as e:
            last_exception = e
            if _is_retryable(e):
                logger.warning("POST %s 失败（第 %d/%d 次尝试）: %s", url, attempt, max_retries, e)
            else:
                logger.error("POST %s 失败: %s", url, e)
                break

        if attempt < max_retries:
            time.sleep(1.0 * attempt)

    raise XDFNetworkError(
        f"请求失败（{url}）: {last_exception}",
        code="NETWORK_ERROR",
    )


def _get_json(
    url: str,
    env: XDFEnvConfig,
    *,
    timeout: float = 15.0,
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    向 XDF API 发送带完整签名头的 JSON GET 请求。

    签名数据 = path + "?" + query（无请求体）。

    参数:
        url:          目标 URL。
        env:          XDF 环境配置。
        timeout:      每次尝试的请求超时时间，以秒为单位。
        max_retries:  临时故障时的最大重试次数。

    返回:
        已解析的 JSON 响应体。

    抛出:
        XDFNetworkError: 所有重试耗尽时。
    """
    ctx = _RequestContext(env)
    parsed = urlparse(url)
    path_and_query = parsed.path + ("?" + parsed.query if parsed.query else "")
    headers = build_signature_headers(path_and_query, None, env, ctx.device_info)

    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout as e:
            last_exception = e
            logger.warning("GET %s 超时（第 %d/%d 次尝试）", url, attempt, max_retries)
        except requests.exceptions.ConnectionError as e:
            last_exception = e
            logger.warning("GET %s 连接错误（第 %d/%d 次尝试）", url, attempt, max_retries)
        except requests.exceptions.HTTPError as e:
            last_exception = e
            if e.response is not None and e.response.status_code >= 500:
                logger.warning("GET %s HTTP %d（第 %d/%d 次尝试）", url, e.response.status_code, attempt, max_retries)
            else:
                logger.error("GET %s HTTP %d: %s", url, e.response.status_code if e.response else 0, e)
                break
        except (requests.exceptions.JSONDecodeError, json.JSONDecodeError) as e:
            last_exception = e
            logger.error("GET %s 返回非 JSON 响应", url)
            break
        except requests.exceptions.RequestException as e:
            last_exception = e
            if _is_retryable(e):
                logger.warning("GET %s 失败（第 %d/%d 次尝试）: %s", url, attempt, max_retries, e)
            else:
                logger.error("GET %s 失败: %s", url, e)
                break

        if attempt < max_retries:
            time.sleep(1.0 * attempt)

    raise XDFNetworkError(
        f"请求失败（{url}）: {last_exception}",
        code="NETWORK_ERROR",
    )
