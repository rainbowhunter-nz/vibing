"""Live devcontainer status: in-flight transient wins, else live Docker truth."""

from vibing_api.core.vocabularies import DevcontainerStatus


def resolve_status(
    transient: DevcontainerStatus | None,
    running_folders: set[str],
    local_path: str,
) -> DevcontainerStatus:
    if transient is not None:
        return transient
    if local_path in running_folders:
        return DevcontainerStatus.RUNNING
    return DevcontainerStatus.STOPPED
