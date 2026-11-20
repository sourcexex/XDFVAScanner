"""XDF 认证客户端 — 登录、学生列表和 IM 凭证获取。"""

import logging

from .config import ENV_PROD, XDFEnvConfig, APP_VERSION
from .crypto import aes_encrypt
from .errors import XDFAuthError
from .http import _post_json, _get_json
from .models import IMCredential, LoginResult, StudentProfile

logger = logging.getLogger("xdflib.auth")


class XDFAuthClient:
    """
    XDF Pad 认证协议客户端。

    处理手机号+密码登录、学生列表获取和 IM/Agora/白板凭证获取。

    使用示例:
        auth = XDFAuthClient(env=ENV_PROD)
        result = auth.login(mobile="138...", password="...")
        students = auth.fetch_student_list(u2at=result.u2at, u2_user_id=result.u2_user_id)
        cred = auth.fetch_im_credential(u2at=result.u2at, student_code=..., school_id=...)
    """

    def __init__(self, env: XDFEnvConfig = ENV_PROD):
        self.env = env

    # ── 密码登录 ─────────────────────────────────────────────

    def login(self, mobile: str, password: str) -> LoginResult:
        """
        使用手机号 + 密码登录 XDF。

        对应 API: POST {login_api}/sdkapi/login/account
        """
        encrypted_mobile = aes_encrypt(mobile, self.env.u2_en32_key)
        encrypted_password = aes_encrypt(password, self.env.u2_en32_key)

        body = {
            "userName": encrypted_mobile,
            "password": encrypted_password,
            "manMachineToken": self.env.t3_id,
        }

        logger.info("正在登录 (mobile=%s***)...", mobile[:3])

        url = f"{self.env.login_api}/sdkapi/login/account"
        resp = _post_json(url, body, self.env)

        # 响应格式: {success: true, status: "1", data: {...}}
        if resp.get("success") and resp.get("status") == "1":
            data = resp.get("data", {})
            logger.info("登录成功 (u2UserId=%s)", data.get("u2UserId", "?"))
            return LoginResult(
                success=True,
                u2_user_id=data.get("u2UserId", ""),
                u2at=data.get("u2at", ""),
                u2at_expire=data.get("u2atExpire", ""),
                mobile=data.get("mobile", ""),
                is_new_user=data.get("newUser", False),
            )
        else:
            error_msg = resp.get("msg", resp.get("Message", "未知错误"))
            logger.error("登录失败: %s", error_msg)
            return LoginResult(
                success=False,
                error_code=resp.get("status", "-1"),
                error_msg=error_msg,
            )

    # ── 获取学生列表 ─────────────────────────────────────────

    def fetch_student_list(self, u2_user_id: str, u2at: str) -> list[StudentProfile]:
        """
        获取当前 U2 账户下的学生档案。

        对应 API: GET {user_center}/usercenter/v3/accounts/students

        参数:
            u2_user_id: 来自 LoginResult 的 U2 用户 ID。
            u2at:       来自 LoginResult 的访问 Token。

        返回:
            学生档案列表。
        """
        url = (
            f"{self.env.user_center_api}/usercenter/v3/accounts/students"
            f"?userId={u2_user_id}&ifPortrait=false"
        )

        logger.info("正在获取学生列表 (userId=%s)...", u2_user_id)
        resp = _get_json(url, self.env)

        # 响应格式: {status: "1", success: true, data: {rows: [...]}}
        if resp.get("status") == "1" or resp.get("success"):
            data = resp.get("data", {})
            rows = data.get("rows", [])
            students: list[StudentProfile] = []
            for row in rows:
                student_codes_list = row.get("studentCodes", [])
                if student_codes_list:
                    for sc in student_codes_list:
                        students.append(StudentProfile(
                            student_code=str(sc.get("studentCode", "")),
                            school_id=str(sc.get("schoolId", "")),
                            school_name=str(sc.get("schoolName", "")),
                            student_id=str(row.get("studentId", "")),
                            user_id=str(row.get("userId", "")),
                            real_name=str(row.get("realName", "")),
                            grade_name=str(row.get("gradeName", "")),
                            mobile=str(row.get("mobile", "")),
                            portrait_url=str(row.get("portraitUrl", "")),
                            gender=row.get("gender", 0),
                            age=row.get("age", 0),
                        ))
                else:
                    students.append(StudentProfile(
                        student_code=str(row.get("studentCode", "")),
                        school_id=str(row.get("schoolId", "")),
                        school_name=str(row.get("schoolName", "")),
                        student_id=str(row.get("studentId", "")),
                        user_id=str(row.get("userId", "")),
                        real_name=str(row.get("realName", "")),
                        grade_name=str(row.get("gradeName", "")),
                        mobile=str(row.get("mobile", "")),
                        portrait_url=str(row.get("portraitUrl", "")),
                        gender=row.get("gender", 0),
                        age=row.get("age", 0),
                    ))
            logger.info("获取到 %d 个学生档案", len(students))
            return students
        else:
            msg = resp.get("msg", resp.get("Message", "未知错误"))
            raise XDFAuthError(f"获取学生列表失败: {msg}", code=resp.get("status"))

    # ── 获取 IM 凭证 ─────────────────────────────────────────

    def fetch_im_credential(
        self,
        u2at: str,
        student_code: str,
        school_id: str = "",
        *,
        timeout: float = 15.0,
        max_retries: int = 3,
    ) -> IMCredential:
        """
        获取 IM + Agora + 白板凭证。

        对应 API: GET {gateway}/api/account/im/agora

        参数:
            u2at:         来自 LoginResult 的 U2 访问 Token（Bearer 令牌）。
            student_code: 学生代码。
            school_id:    学校 ID（可选）。
            timeout:      请求超时时间。
            max_retries:  最大重试次数。

        返回:
            包含 IM 用户 ID + UserSig、Agora 应用 ID + Token、白板凭证的 IMCredential。
        """
        import time as _time
        import requests as _requests

        url = f"{self.env.gateway_api}/api/account/im/agora"
        headers = {
            "authorization": u2at,
            "studentCode": student_code,
            "schoolId": school_id,
            "platform": "android",
            "appVersion": APP_VERSION,
            "systemVersion": "11",
        }

        logger.info("正在获取 IM 凭证 (studentCode=%s)...", student_code)

        last_error: str = ""
        for attempt in range(1, max_retries + 1):
            try:
                resp = _requests.get(url, headers=headers, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                break  # 成功，跳出重试循环
            except _requests.exceptions.Timeout:
                last_error = "连接超时"
                logger.warning("IM 凭证请求超时（第 %d/%d 次尝试）", attempt, max_retries)
            except _requests.exceptions.ConnectionError as e:
                last_error = str(e)
                logger.warning("IM 凭证连接错误（第 %d/%d 次尝试）", attempt, max_retries)
            except _requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code >= 500:
                    last_error = f"HTTP {e.response.status_code}"
                    logger.warning("IM 凭证 HTTP %d（第 %d/%d 次尝试）", e.response.status_code, attempt, max_retries)
                else:
                    logger.error("获取 IM 凭证失败: %s", e)
                    return IMCredential(success=False, error_msg=str(e))
            except _requests.exceptions.RequestException as e:
                last_error = str(e)
                logger.error("获取 IM 凭证失败: %s", e)
                if attempt >= max_retries:
                    return IMCredential(success=False, error_msg=str(e))

            if attempt < max_retries:
                _time.sleep(1.0 * attempt)
        else:
            # 所有重试耗尽（网络级错误）
            return IMCredential(success=False, error_msg=last_error)

        # 网关响应使用 code=="200"（而非 status=="1"）
        if data.get("code") == "200" or data.get("success"):
            inner = data.get("data", data)
            logger.info("获取 IM 凭证成功 (imStudentId=%s)", inner.get("imStudentId", "?"))
            return IMCredential(
                success=True,
                im_student_id=inner.get("imStudentId", ""),
                im_student_sig=inner.get("imStudentSig", ""),
                student_code=inner.get("studentCode", student_code),
                agora_app_id=inner.get("agoraAppId", ""),
                agora_token=inner.get("agoraToken", ""),
                agora_user_id=inner.get("agoraUserId", 0),
                wb_user_id=inner.get("wbUserId", ""),
                wb_user_sign=inner.get("wbUserSign", ""),
            )
        else:
            return IMCredential(
                success=False,
                error_code=data.get("code", "-1"),
                error_msg=data.get("message", data.get("msg", "获取 IM 凭证失败")),
            )

    # ── 组合流程 ────────────────────────────────────────────

    def login_and_fetch_im(
        self, mobile: str, password: str, student_code: str = ""
    ) -> tuple[LoginResult, IMCredential | None, list[StudentProfile]]:
        """
        登录并获取 IM 凭证（完整三步流程）。

        返回:
            (login_result, im_credential, student_list)
        """
        # 第 1 步：登录
        login_result = self.login(mobile, password)
        if not login_result.success:
            return login_result, None, []

        # 第 2 步：获取学生列表
        students = self.fetch_student_list(login_result.u2_user_id, login_result.u2at)
        if not students:
            logger.warning("未找到学生档案，尝试以空凭证获取 IM 信息...")
            im_cred = self.fetch_im_credential(login_result.u2at, "", "")
            return login_result, im_cred, []

        # 第 3 步：选择学生并获取 IM 凭证
        if student_code:
            selected = next((s for s in students if s.student_code == student_code), None)
            if not selected:
                selected = students[0]
                logger.warning("学生代码 %s 未找到，使用第一个: %s", student_code, selected.student_code)
        else:
            selected = students[0]
            if len(students) > 1:
                logger.info("找到 %d 个学生，默认使用: %s", len(students), selected.real_name or selected.student_code)

        im_cred = self.fetch_im_credential(
            login_result.u2at, selected.student_code, selected.school_id
        )
        return login_result, im_cred, students
