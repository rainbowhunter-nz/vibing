import asyncio
import sys

from vibing_devcontainer_runtime.harness.process import (
    CompletedCommand,
    real_process_factory,
    run_to_completion,
)


def test_real_factory_runs_and_captures_stdout_and_exit():
    result = asyncio.run(
        run_to_completion(real_process_factory, [sys.executable, "-c", "print('hi')"])
    )
    assert isinstance(result, CompletedCommand)
    assert result.returncode == 0
    assert result.stdout.strip() == "hi"


def test_real_factory_missing_binary_returns_127_not_raise():
    result = asyncio.run(run_to_completion(real_process_factory, ["definitely-not-a-binary-xyz"]))
    assert result.returncode == 127


def test_extra_env_is_passed_to_child():
    code = "import os; print(os.environ.get('VIBING_TEST_VAR', 'missing'))"
    result = asyncio.run(
        run_to_completion(
            real_process_factory, [sys.executable, "-c", code], env={"VIBING_TEST_VAR": "present"}
        )
    )
    assert result.stdout.strip() == "present"
