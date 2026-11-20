#!/usr/bin/env python3
"""调试登录 —— 对单个账号发起登录请求，打印原始 API 返回。

用法:
    xdf-debug-login --mobile 13800138000 --password mypassword
    python -m xdfvafinder.debug_login --mobile 13800138000 --password mypassword --env test
"""

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from xdflib import ENV_PROD, XDFAuthClient
from xdflib.config import XDFEnvConfig
from xdflib.crypto import aes_encrypt, build_signature_headers, generate_device_info
from xdflib.models import LoginResult

from .env import ENV_CHOICES, resolve_env

LOGIN_PATH = "/sdkapi/login/account"
SEPARATOR = "=" * 70

__all__ = ["debug_login", "main"]


@dataclass
class _Request:
    """一次待发送的登录请求。"""

    url: str
    body: dict[str, str]
    body_json: str
    headers: dict[str, str]
    encrypted_mobile: str
    encrypted_password: str


def _build_request(mobile: str, password: str, env: XDFEnvConfig) -> _Request:
    """按 XDF 协议构造登录请求：AES 加密用户名/密码 + 完整签名头。"""
    encrypted_mobile = aes_encrypt(mobile, env.u2_en32_key)
    encrypted_password = aes_encrypt(password, env.u2_en32_key)
    body = {
        "userName": encrypted_mobile,
        "password": encrypted_password,
        "manMachineToken": env.t3_id,
    }

    url = f"{env.login_api}{LOGIN_PATH}"
    parsed = urlparse(url)
    path_and_query = parsed.path + ("?" + parsed.query if parsed.query else "")
    headers = build_signature_headers(path_and_query, body, env, generate_device_info())

    return _Request(
        url=url,
        body=body,
        body_json=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        headers=headers,
        encrypted_mobile=encrypted_mobile,
        encrypted_password=encrypted_password,
    )


def _print_request(request: _Request, *, mobile: str, password: str, env: XDFEnvConfig) -> None:
    """打印请求概况：环境、加密结果、请求体与签名头。"""
    print(SEPARATOR)
    print("  XDF 登录调试")
    print(SEPARATOR)
    print(f"  环境:       {'PROD' if env is ENV_PROD else 'TEST'}")
    print(f"  Login API:  {request.url}")
    print(f"  手机号:     {mobile}")
    print(f"  密码:       {password}")
    print(f"  t3_id:      {env.t3_id}")
    print()

    print(f"  加密后 userName:  {request.encrypted_mobile[:60]}...")
    print(f"  加密后 password:  {request.encrypted_password[:60]}...")
    print()

    print("  请求体 (JSON):")
    print(f"    {json.dumps(request.body, ensure_ascii=False)}")
    print()

    print("  签名头:")
    for name, value in request.headers.items():
        if name == "User-Agent":
            print(f"    {name}: {value}")
        else:
            print(f"    {name}: {value[:80]}{'...' if len(value) > 80 else ''}")
    print()


def _print_response(response: requests.Response, elapsed: float) -> dict[str, Any] | None:
    """打印响应耗时、状态码、响应头与原始响应体；非 JSON 时返回 ``None``。"""
    print(f"  响应耗时: {elapsed:.2f}s")
    print(f"  HTTP 状态码: {response.status_code}")
    print()
    print("  ── 响应头 ──")
    for name, value in response.headers.items():
        print(f"    {name}: {value}")
    print()
    print("  ── 响应体 (原始 JSON) ──")

    try:
        payload = response.json()
    except ValueError:
        print(f"    (非 JSON) {response.text[:500]}")
        print()
        return None

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    return payload


def _explain_payload(payload: dict[str, Any]) -> None:
    """按 auth.py 的判定逻辑解释响应，并说明成功/失败原因。"""
    print("  ── auth.py 解析结果 ──")
    success = payload.get("success")
    status = payload.get("status")
    code = payload.get("code")
    message = payload.get("msg", payload.get("Message", ""))
    data = payload.get("data", {})

    print(f"    resp['success'] = {success!r}  (type={type(success).__name__})")
    print(f"    resp['status']  = {status!r}   (type={type(status).__name__})")
    print(f"    resp['code']    = {code!r}     (type={type(code).__name__})")
    print(f"    resp['msg']     = {message!r}")
    print()

    accepted = bool(success) and status == "1"
    print(f"    auth.py 判断: success and status=='1' → {accepted}")
    print()

    if accepted:
        print("    ✓ auth.py 会判定为【登录成功】")
        print(f"      u2UserId:  {data.get('u2UserId', '?')}")
        print(f"      u2at:      {(data.get('u2at', '') or '')[:40]}...")
        print(f"      mobile:    {data.get('mobile', '?')}")
        return

    print("    ✗ auth.py 会判定为【登录失败】")
    reasons = []
    if not success:
        reasons.append("success 字段为 falsy")
    if status != "1":
        reasons.append(f"status 字段为 {status!r} 而不是 '1'")
    print(f"    原因: {'; '.join(reasons) or '未知原因'}")
    print(f"    error_code: {status!r}")
    print(f"    error_msg:  {message!r}")


def _print_login_result(result: LoginResult) -> None:
    """打印 XDFAuthClient.login() 的解析结果，用于和原始响应对照。"""
    print()
    print("  ── XDFAuthClient.login() 对比 ──")
    print(f"    result.success:     {result.success}")
    print(f"    result.u2_user_id:  {result.u2_user_id!r}")
    print(f"    result.error_code:  {result.error_code!r}")
    print(f"    result.error_msg:   {result.error_msg!r}")
    print(f"    result.is_new_user: {result.is_new_user}")


def _print_students(auth: XDFAuthClient, result: LoginResult) -> None:
    """登录成功后打印学员列表。"""
    print()
    print("  ── 学员列表 ──")
    try:
        students = auth.fetch_student_list(result.u2_user_id, result.u2at)
    except Exception as exc:  # noqa: BLE001
        print(f"    获取失败: {exc}")
        return

    if not students:
        print("    (无学员)")
        return

    for index, student in enumerate(students, start=1):
        print(f"    [{index}] 学员ID:    {student.student_id}")
        print(f"        学员编号:  {student.student_code}")
        print(f"        姓名:      {student.real_name}")
        print(f"        年级:      {student.grade_name}")
        print(f"        学校ID:    {student.school_id}")
        print(f"        学校名:    {student.school_name}")
        print()


def debug_login(
    mobile: str,
    password: str,
    env: XDFEnvConfig,
    *,
    timeout: float = 15.0,
) -> bool:
    """发起原始登录请求并打印全部调试信息；返回请求是否成功发出。"""
    request = _build_request(mobile, password, env)
    _print_request(request, mobile=mobile, password=password, env=env)

    print("  发送 POST 请求...")
    started = time.monotonic()
    try:
        response = requests.post(
            request.url,
            data=request.body_json,
            headers=request.headers,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"\n  ✗ 请求失败: {exc}")
        print(SEPARATOR)
        return False

    payload = _print_response(response, time.monotonic() - started)
    if payload is None:
        print(SEPARATOR)
        return True

    _explain_payload(payload)

    auth = XDFAuthClient(env=env)
    result = auth.login(mobile, password)
    _print_login_result(result)
    if result.success:
        _print_students(auth, result)

    print(SEPARATOR)
    return True


def build_parser() -> argparse.ArgumentParser:
    """构造调试登录命令行解析器。"""
    parser = argparse.ArgumentParser(description="XDF 登录调试工具")
    parser.add_argument("--mobile", "-m", required=True, help="手机号")
    parser.add_argument("--password", "-p", required=True, help="密码")
    parser.add_argument(
        "--env", choices=ENV_CHOICES, default="prod", help="环境 (默认: prod，测试请用 test)"
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="请求超时秒数 (默认: 15)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口；请求失败返回 1。"""
    args = build_parser().parse_args(argv)
    ok = debug_login(args.mobile, args.password, resolve_env(args.env), timeout=args.timeout)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
