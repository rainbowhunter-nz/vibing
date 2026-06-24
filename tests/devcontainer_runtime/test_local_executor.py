import asyncio

from vibing_devcontainer_runtime.local_executor import LocalExecutor


def test_run_executes_real_command(tmp_path):
    ex = LocalExecutor(home=tmp_path)
    result = asyncio.run(ex.run(["bash", "-c", "echo hi"]))
    assert result.returncode == 0
    assert "hi" in result.stdout


def test_run_passes_env_to_subprocess(tmp_path):
    ex = LocalExecutor(home=tmp_path)
    result = asyncio.run(ex.run(["bash", "-c", "echo $MY_VAR"], env={"MY_VAR": "hello"}))
    assert result.returncode == 0
    assert "hello" in result.stdout


def test_run_missing_binary_returns_127(tmp_path):
    ex = LocalExecutor(home=tmp_path)
    result = asyncio.run(ex.run(["definitely-not-a-binary-xyz"]))
    assert result.returncode == 127


def test_write_then_read_round_trip_home_relative(tmp_path):
    ex = LocalExecutor(home=tmp_path)
    asyncio.run(ex.write(".config/x/cred.json", b"secret", mode=0o600))
    path = tmp_path / ".config" / "x" / "cred.json"
    assert path.read_bytes() == b"secret"
    assert (path.stat().st_mode & 0o777) == 0o600
    assert asyncio.run(ex.read(".config/x/cred.json")) == b"secret"


def test_read_absent_returns_none(tmp_path):
    assert asyncio.run(LocalExecutor(home=tmp_path).read("nope")) is None
