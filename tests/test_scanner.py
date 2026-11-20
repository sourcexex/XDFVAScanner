"""扫描器逻辑测试（网络层全部 mock，不产生真实请求）。"""

import json
from unittest import mock

import xdflib.auth as auth_mod
from xdfvafinder.scanner import Scanner

LOGIN_OK = {"success": True, "status": "1", "data": {"u2UserId": "u2-1", "u2at": "tok"}}
LOGIN_REJECTED = {"success": False, "status": "0", "msg": "账号或密码错误"}
STUDENTS_OK = {
    "status": "1",
    "data": {
        "rows": [
            {
                "studentId": "s1",
                "studentCode": "c1",
                "realName": "张三",
                "gradeName": "初一",
                "schoolId": "9",
                "schoolName": "XDF 学校",
            }
        ]
    },
}


def _scanner(tmp_path, **overrides) -> Scanner:
    options = {
        "start": 0,
        "end": 2,
        "threads": 2,
        "delay": 0,
        "env": "test",
        "output": tmp_path / "valid_accounts.txt",
        "checkpoint_file": tmp_path / "scan_progress.json",
    }
    options.update(overrides)
    return Scanner(**options)


def _rows(path) -> list[str]:
    return [
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")
    ]


class TestGenerate:
    def test_mobile_and_password(self):
        assert Scanner.generate(0) == ("14400000444", "XdFopt00000")
        assert Scanner.generate(12345) == ("14412345444", "XdFopt12345")
        assert Scanner.generate(99999) == ("14499999444", "XdFopt99999")

    def test_pads_to_five_digits(self):
        assert Scanner.generate(7)[0] == "14400007444"


class TestTryLogin:
    def test_success_fetches_students(self, tmp_path):
        with (
            mock.patch.object(auth_mod, "_post_json", return_value=LOGIN_OK),
            mock.patch.object(auth_mod, "_get_json", return_value=STUDENTS_OK),
        ):
            outcome = _scanner(tmp_path).try_login(12345)

        assert outcome.success
        assert outcome.mobile == "14412345444"
        assert outcome.u2_user_id == "u2-1"
        assert [student.student_id for student in outcome.students] == ["s1"]

    def test_rejected_account(self, tmp_path):
        with mock.patch.object(auth_mod, "_post_json", return_value=LOGIN_REJECTED):
            outcome = _scanner(tmp_path).try_login(0)

        assert not outcome.success
        assert outcome.error_msg == "账号或密码错误"
        assert outcome.error_type is None
        assert outcome.students == []

    def test_student_fetch_failure_keeps_login(self, tmp_path):
        with (
            mock.patch.object(auth_mod, "_post_json", return_value=LOGIN_OK),
            mock.patch.object(auth_mod, "_get_json", side_effect=RuntimeError("boom")),
        ):
            outcome = _scanner(tmp_path).try_login(0)

        assert outcome.success
        assert outcome.students == []

    def test_exception_is_network_error(self, tmp_path):
        with mock.patch.object(auth_mod, "_post_json", side_effect=RuntimeError("boom")):
            outcome = _scanner(tmp_path).try_login(0)

        assert not outcome.success
        assert outcome.error_type == "network"

    def test_stop_event_short_circuits(self, tmp_path):
        scanner = _scanner(tmp_path)
        scanner.stop_event.set()
        assert scanner.try_login(0).error_type == "stopped"


class TestRun:
    def test_full_run_writes_results_and_checkpoint(self, tmp_path):
        scanner = _scanner(tmp_path)
        with (
            mock.patch.object(auth_mod, "_post_json", return_value=LOGIN_OK),
            mock.patch.object(auth_mod, "_get_json", return_value=STUDENTS_OK),
        ):
            interrupted = scanner.run(install_signals=False)

        assert interrupted is False
        assert (scanner.total_scanned, scanner.valid_count, scanner.invalid_count) == (3, 3, 0)

        rows = _rows(tmp_path / "valid_accounts.txt")
        assert len(rows) == 3
        # 多线程下按完成顺序追加，行序不保证；按手机号排序后校验内容
        rows.sort()
        assert [row.split("|")[0] for row in rows] == [
            "14400000444",
            "14400001444",
            "14400002444",
        ]
        assert rows[0] == "14400000444|XdFopt00000|u2-1|s1|c1|张三|初一|9|XDF 学校"

        state = json.loads((tmp_path / "scan_progress.json").read_text(encoding="utf-8"))
        assert state["last_digits"] == 2
        assert state["end"] == 2
        assert state["env"] == "test"
        assert state["valid_count"] == 3

    def test_resume_skips_scanned_prefix(self, tmp_path):
        (tmp_path / "scan_progress.json").write_text(
            json.dumps(
                {
                    "last_digits": 1,
                    "end": 2,
                    "env": "test",
                    "valid_count": 2,
                    "total_scanned": 2,
                    "updated_at": "x",
                }
            ),
            encoding="utf-8",
        )
        scanner = _scanner(tmp_path, threads=1, resume=True)
        with (
            mock.patch.object(auth_mod, "_post_json", return_value=LOGIN_OK) as post,
            mock.patch.object(auth_mod, "_get_json", return_value=STUDENTS_OK),
        ):
            scanner.run(install_signals=False)

        assert post.call_count == 1  # 只扫描 digits=2
        assert scanner.total_scanned == 3  # 接续断点里记录的 2
        rows = _rows(tmp_path / "valid_accounts.txt")
        assert len(rows) == 1
        assert rows[0].startswith("14400002444|")

    def test_resume_without_checkpoint_scans_everything(self, tmp_path):
        scanner = _scanner(tmp_path, resume=True)
        with mock.patch.object(auth_mod, "_post_json", return_value=LOGIN_REJECTED) as post:
            scanner.run(install_signals=False)

        assert post.call_count == 3

    def test_resume_when_checkpoint_covers_range(self, tmp_path):
        (tmp_path / "scan_progress.json").write_text(
            json.dumps(
                {
                    "last_digits": 2,
                    "end": 2,
                    "env": "test",
                    "valid_count": 3,
                    "total_scanned": 3,
                    "updated_at": "x",
                }
            ),
            encoding="utf-8",
        )
        scanner = _scanner(tmp_path, resume=True)
        with mock.patch.object(auth_mod, "_post_json", return_value=LOGIN_REJECTED) as post:
            assert scanner.run(install_signals=False) is False

        assert post.call_count == 0

    def test_stop_saves_checkpoint_of_contiguous_scan(self, tmp_path):
        scanner = _scanner(tmp_path, start=0, end=9, threads=1)
        handle_result = scanner.handle_result

        def stop_after_first(outcome):
            handle_result(outcome)
            scanner.stop_event.set()

        with (
            mock.patch.object(auth_mod, "_post_json", return_value=LOGIN_REJECTED),
            mock.patch.object(scanner, "handle_result", side_effect=stop_after_first),
        ):
            interrupted = scanner.run(install_signals=False)

        assert interrupted is True
        assert scanner.total_scanned < 10  # 没有把整个号段跑完
        state = json.loads((tmp_path / "scan_progress.json").read_text(encoding="utf-8"))
        assert state["last_digits"] == scanner.total_scanned - 1

    def test_output_file_keeps_header_on_resume(self, tmp_path):
        output = tmp_path / "valid_accounts.txt"
        output.write_text("# 旧内容\n", encoding="utf-8")
        scanner = _scanner(tmp_path, threads=1, resume=True)
        with (
            mock.patch.object(auth_mod, "_post_json", return_value=LOGIN_OK),
            mock.patch.object(auth_mod, "_get_json", return_value=STUDENTS_OK),
        ):
            scanner.run(install_signals=False)

        content = output.read_text(encoding="utf-8")
        assert content.startswith("# 旧内容\n")
        assert len(_rows(output)) == 3
