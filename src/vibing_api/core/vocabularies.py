from enum import StrEnum, auto


class DevcontainerStatus(StrEnum):
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()
