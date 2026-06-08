from __future__ import annotations

import os

import pytest

from moma_cli.main import main


LIVE_TEST_ENV = "MOMA_RUN_LIVE_TESTS"
LIVE_CONFIG_ENV = "MOMA_CLI_E2E_CONFIG"


pytestmark = pytest.mark.skipif(
    os.environ.get(LIVE_TEST_ENV) != "1",
    reason="Set MOMA_RUN_LIVE_TESTS=1 to enable live provider E2E tests.",
)


def test_cli_run_live_provider_smoke(tmp_path) -> None:
    config_path = os.environ.get(LIVE_CONFIG_ENV)
    if not config_path:
        pytest.skip("Set MOMA_CLI_E2E_CONFIG to a valid config file for live CLI E2E tests.")

    exit_code = main(
        [
            "--config",
            config_path,
            "--workspace",
            str(tmp_path / "workspace"),
            "run",
            "你是谁，请用一句话回答。",
        ]
    )

    assert exit_code == 0
