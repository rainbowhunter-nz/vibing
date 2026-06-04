from enum import StrEnum, auto


class DevcontainerStatus(StrEnum):
    CREATED = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()


class AgentSessionStatus(StrEnum):
    STARTING = auto()
    RUNNING = auto()
    WAITING_FOR_APPROVAL = auto()
    COMPLETED = auto()
    FAILED = auto()
    STOPPED = auto()


class ApprovalStatus(StrEnum):
    PENDING = auto()
    APPROVED = auto()
    REJECTED = auto()


class InboxEventType(StrEnum):
    QUESTION = auto()
    APPROVAL_REQUEST = auto()
    COMPLETION = auto()
    FAILURE = auto()


class InboxEventStatus(StrEnum):
    UNREAD = auto()
    READ = auto()
    RESOLVED = auto()
