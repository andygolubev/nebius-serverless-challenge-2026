"""Pydantic request/response models for the demo training API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TrainRequest(BaseModel):
    """Body for ``POST /train``.

    ``extra="forbid"`` rejects any field that is not an allowlisted safe
    parameter -- in particular arbitrary environment IDs, images, commands, code
    paths, or reward functions.
    """

    model_config = ConfigDict(extra="forbid")

    preset: str = Field(..., description="Allowlisted preset name")
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    render_progress_video: bool | None = Field(default=None)

    def safe_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.seed is not None:
            params["seed"] = self.seed
        if self.render_progress_video is not None:
            params["render_progress_video"] = self.render_progress_video
        return params


class TrainResponse(BaseModel):
    run_id: str
    status: str
    status_url: str


class HealthResponse(BaseModel):
    status: str
    backend: str
