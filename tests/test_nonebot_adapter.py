from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("custom_cache_dir", [False, True])
def test_real_nonebot_event_chain_in_isolated_process(tmp_path, custom_cache_dir):
    pytest.importorskip("nonebot.adapters.onebot.v11")
    pytest.importorskip("fastapi")
    script = Path(__file__).with_name("nonebot_case.py")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("VOLT_TEST_CACHE_DIR", None)
    if custom_cache_dir:
        env["VOLT_TEST_CACHE_DIR"] = str(tmp_path / "custom-cache")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nonebot adapter regression passed" in result.stdout
