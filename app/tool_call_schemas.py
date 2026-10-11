
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_ARGUMENTS_BYTES = 10_000


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: int = Field(gt=0)
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("arguments")
    @classmethod
    def limit_arguments_size(
        cls,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        import json

        try:
            serialized = json.dumps(
                arguments,
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError(
                "Arguments must contain valid JSON-compatible values."
            ) from exc

        if len(serialized) > MAX_ARGUMENTS_BYTES:
            raise ValueError(
                "Arguments exceed the maximum allowed size of 10000 bytes."
            )

        return arguments
