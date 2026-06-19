"""build_adapters: name -> HarnessAdapter. The list of managed harnesses lives here."""

from pathlib import Path

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.codex import CodexAdapter
from vibing_devcontainer_runtime.harness.cursor import CursorAdapter
from vibing_devcontainer_runtime.harness.process import HarnessProcessFactory, real_process_factory


def build_adapters(
    factory: HarnessProcessFactory | None = None, home: Path | None = None
) -> dict[str, HarnessAdapter]:
    factory = factory or real_process_factory
    home = home or Path.home()
    adapters: list[HarnessAdapter] = [CodexAdapter(factory, home), CursorAdapter(factory, home)]
    return {a.name: a for a in adapters}
