"""命令行入口测试（不产生真实请求）。"""

import pytest

from xdfvafinder import debug_login as debug_login_mod
from xdfvafinder import scanner as scanner_mod


@pytest.fixture
def no_logging(monkeypatch):
    """避免测试在仓库目录里生成 scan.log。"""
    monkeypatch.setattr(scanner_mod, "setup_logging", lambda **kwargs: None)


class TestScannerCli:
    def test_start_greater_than_end_exits_2(self, no_logging):
        with pytest.raises(SystemExit) as exc:
            scanner_mod.main(["--start", "5", "--end", "1"])
        assert exc.value.code == 2

    @pytest.mark.parametrize(
        "args",
        [
            ["--start", "100000"],
            ["--end", "-1"],
            ["--threads", "0"],
            ["--delay", "-1"],
            ["--env", "staging"],
        ],
    )
    def test_invalid_args_exit_2(self, no_logging, args):
        with pytest.raises(SystemExit) as exc:
            scanner_mod.main(args)
        assert exc.value.code == 2

    def test_interrupted_run_exits_130(self, no_logging, monkeypatch):
        monkeypatch.setattr(scanner_mod.Scanner, "run", lambda self, **kwargs: True)
        assert scanner_mod.main(["--start", "0", "--end", "0", "--env", "test"]) == 130

    def test_normal_run_exits_0(self, no_logging, monkeypatch):
        monkeypatch.setattr(scanner_mod.Scanner, "run", lambda self, **kwargs: False)
        assert scanner_mod.main(["--start", "0", "--end", "0", "--env", "test"]) == 0

    def test_checkpoint_and_log_flags(self, monkeypatch, tmp_path):
        monkeypatch.setattr(scanner_mod.Scanner, "run", lambda self, **kwargs: False)
        log_file = tmp_path / "run.log"
        checkpoint = tmp_path / "checkpoint.json"

        assert (
            scanner_mod.main(
                [
                    "--env",
                    "test",
                    "--checkpoint",
                    str(checkpoint),
                    "--log-file",
                    str(log_file),
                ]
            )
            == 0
        )
        assert log_file.exists()


class TestDebugLoginCli:
    def test_request_failure_exits_1(self, monkeypatch):
        monkeypatch.setattr(debug_login_mod, "debug_login", lambda *args, **kwargs: False)
        assert (
            debug_login_mod.main(["-m", "14400000444", "-p", "XdFopt00000", "--env", "test"]) == 1
        )

    def test_success_exits_0(self, monkeypatch):
        monkeypatch.setattr(debug_login_mod, "debug_login", lambda *args, **kwargs: True)
        assert (
            debug_login_mod.main(["-m", "14400000444", "-p", "XdFopt00000", "--env", "test"]) == 0
        )

    def test_missing_credentials_exit_2(self):
        with pytest.raises(SystemExit) as exc:
            debug_login_mod.main([])
        assert exc.value.code == 2
