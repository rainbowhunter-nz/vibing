from enum import StrEnum, auto


class DevcontainerStatus(StrEnum):
    CREATED = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()
