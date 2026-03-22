from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, Field

AgentStatus = str
CommandStatus = str
ModelT = TypeVar("ModelT", bound=BaseModel)


class AgentRegistration(BaseModel):
    agent_id: str = Field(min_length=1)
    display_name: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRecord(AgentRegistration):
    status: AgentStatus = "online"
    created_at: str
    updated_at: str
    last_seen: str


class EnqueueCommandRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    command: str = Field(min_length=1)
    requested_by: str = "tui"
    timeout_seconds: int = Field(default=60, ge=1, le=3600)


class CommandRecord(BaseModel):
    command_id: str
    agent_id: str
    command: str
    requested_by: str
    timeout_seconds: int
    status: CommandStatus
    created_at: str
    leased_at: str | None = None
    completed_at: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


class CommandLease(BaseModel):
    command: CommandRecord | None = None


class CommandResultUpdate(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str = ""


def dump_model(model: BaseModel, **kwargs: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


def validate_model(model_cls: type[ModelT], payload: Any) -> ModelT:
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(payload)
    return model_cls.parse_obj(payload)
