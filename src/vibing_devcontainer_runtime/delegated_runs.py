"""DelegatedRunManager: runs managed harnesses unattended (ADR-0013).

Concurrent up to a cap; each run is a HarnessProcess tracked by run id. Runs are not
durable — results live in memory for the process lifetime. Delegated runs are in-container
only (ADR-0015 Q9=A); no upward event emission.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.process import HarnessProcess, HarnessProcessFactory


@dataclass
class _Run:
    run_id: str
    harness: str
    model: str
    status: str = "running"  # running | completed | failed | stopped
    result: str = ""
    error: dict[str, Any] = field(default_factory=dict)
    process: HarnessProcess | None = None
    task: asyncio.Task[None] | None = None


class DelegatedRunManager:
    def __init__(
        self,
        adapters: dict[str, HarnessAdapter],
        factory: HarnessProcessFactory,
        *,
        devcontainer_id: str,
        workspace: str,
        max_concurrent: int = 4,
    ) -> None:
        self._adapters = adapters
        self._factory = factory
        self._devcontainer_id = devcontainer_id
        self._workspace = workspace
        self._max = max_concurrent
        self._runs: dict[str, _Run] = {}
        self._counter = 0

    def _active(self) -> int:
        return sum(1 for r in self._runs.values() if r.status == "running")

    async def spawn(
        self,
        harness: str,
        model: str,
        prompt: str,
        *,
        cwd: str | None = None,
        detached: bool = False,
    ) -> dict[str, Any]:
        adapter = self._adapters[harness]  # KeyError on unknown harness
        if not await adapter.is_authenticated():
            raise RuntimeError(f"harness {harness} is not authenticated")
        if self._active() >= self._max:
            raise RuntimeError("delegated runs at capacity")

        self._counter += 1
        run = _Run(run_id=f"run-{self._counter}", harness=harness, model=model)
        self._runs[run.run_id] = run

        argv = adapter.build_spawn_argv(model, prompt)
        run.process = self._factory(argv, cwd or self._workspace, adapter.spawn_env())

        if detached:
            run.task = asyncio.create_task(self._await_run(run, adapter))
            return {"run_id": run.run_id, "status": "running"}
        await self._await_run(run, adapter)
        if run.status == "completed":
            return {"run_id": run.run_id, "status": "completed", "result": run.result}
        return {"run_id": run.run_id, "status": "failed", "error": run.error}

    async def _await_run(self, run: _Run, adapter: HarnessAdapter) -> None:
        assert run.process is not None
        try:
            result = await run.process.wait()
        except asyncio.CancelledError:
            run.status = "stopped"
            raise
        except Exception as exc:
            run.status = "failed"
            run.error = {"exit_code": None, "stderr_tail": str(exc)[-4000:]}
            return
        if result.returncode == 0:
            run.status = "completed"
            run.result = adapter.extract_result(result.stdout)
        else:
            run.status = "failed"
            run.error = {"exit_code": result.returncode, "stderr_tail": result.stderr[-4000:]}

    def _get(self, run_id: str) -> _Run:
        return self._runs[run_id]  # KeyError on unknown run

    def get_status(self, run_id: str) -> dict[str, Any]:
        run = self._get(run_id)
        return {"run_id": run_id, "status": run.status}

    def get_result(self, run_id: str) -> dict[str, Any]:
        run = self._get(run_id)
        return {"run_id": run_id, "status": run.status, "result": run.result, "error": run.error}

    async def stop(self, run_id: str) -> dict[str, Any]:
        run = self._get(run_id)
        if run.task is not None and not run.task.done():
            run.task.cancel()
            try:
                await run.task
            except BaseException:  # task already cancelled or errored; we only need it reaped
                pass
        if run.process is not None:
            await run.process.terminate()
        if run.status == "running":
            run.status = "stopped"
        return {"run_id": run_id, "status": run.status}

    async def wait_all(self) -> None:
        tasks = [r.task for r in self._runs.values() if r.task is not None and not r.task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
