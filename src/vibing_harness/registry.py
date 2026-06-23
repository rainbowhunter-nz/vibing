"""descriptors(): name -> HarnessDescriptor. The managed-harness list lives here."""

from vibing_harness.base import HarnessDescriptor
from vibing_harness.descriptors.codex import CodexDescriptor
from vibing_harness.descriptors.cursor import CursorDescriptor


def descriptors() -> dict[str, HarnessDescriptor]:
    items: list[HarnessDescriptor] = [CodexDescriptor(), CursorDescriptor()]
    return {d.name: d for d in items}
