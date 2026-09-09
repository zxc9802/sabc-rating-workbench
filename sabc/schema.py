"""Validate proposals at both model and HTTP boundaries."""
import math
from typing import Literal

from pydantic import BaseModel, Field, StrictBool


class Dimension(BaseModel):
    score: float | None = Field(default=None, ge=0, le=5, allow_inf_nan=False, strict=True)
    reason: str = ''
    basis: Literal['fact', 'assumption', 'unknown'] = 'unknown'
    evidence_ids: list[str] = Field(default_factory=list)


class Assumption(BaseModel):
    id: str
    claim: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    validation_method: str = ''
    pass_threshold: str = ''
    fail_threshold: str = ''


class Veto(BaseModel):
    reason: str = Field(min_length=1)
    confirmed: StrictBool = False
    evidence_ids: list[str] = Field(default_factory=list)


class Proposal(BaseModel):
    dimensions: dict[str, Dimension] = Field(default_factory=dict)
    assumptions: list[Assumption] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    policy_caps: list[str] = Field(default_factory=list)
    vetoes: list[Veto] = Field(default_factory=list)
    s_conditions: dict[str, StrictBool] = Field(default_factory=dict)


def validate_amounts(data, fields):
    for field in fields:
        value = data.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise ValueError('预算和现金必须为非负有限数字')


def validate_proposal(data):
    try:
        return Proposal.model_validate(data).model_dump()
    except ValueError:
        raise ValueError('评分建议格式无效，请检查维度、关键假设和确认条件') from None
