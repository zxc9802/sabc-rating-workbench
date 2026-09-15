"""Validate proposals at both model and HTTP boundaries."""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sabc.rating import TYPES


def validate_project_type(data):
    if data.get('project_type') is not None and (not isinstance(data['project_type'], str) or data['project_type'] not in TYPES):
        raise ValueError('请选择有效的项目类型：商业增长、内部AI / 提效、战略能力 / 资产或重资产 / 扩张')


class SourceClaim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=4)
    subject: str = Field(min_length=1)
    scope: Literal['project', 'group', 'industry', 'researcher'] = 'project'
    metric: str = Field(min_length=1)
    period: str = '未注明'
    unit: str = '不适用'
    use: Literal['support', 'background'] = 'support'


class DecisionFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = ''
    kind: Literal['reported', 'suggestion', 'unknown'] = 'unknown'
    source_id: str = ''
    quote: str = ''


class AssessmentScope(BaseModel):
    subject: str = Field(min_length=1)
    level: Literal['project', 'group'] = 'project'
    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=4)
    company_baseline: bool = False
    baseline_source_id: str = ''
    baseline_quote: str = ''


class Dimension(BaseModel):
    score: float | None = Field(default=None, ge=0, le=5, allow_inf_nan=False, strict=True)
    reason: str = ''
    basis: Literal['fact', 'assumption', 'unknown'] = 'unknown'
    evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: str = ''
    negative_fact: str | None = ''
    anchor_score: int | None = Field(default=None, ge=0, le=5)
    support: list[SourceClaim] = Field(default_factory=list, max_length=6)


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
    grounding_version: int = 0
    assessment_scope: AssessmentScope | None = None
    decision_facts: dict[str, DecisionFact] = Field(default_factory=dict)
    dimensions: dict[str, Dimension] = Field(default_factory=dict)
    assumptions: list[Assumption] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    policy_caps: list[str] = Field(default_factory=list)
    vetoes: list[Veto] = Field(default_factory=list)
    s_conditions: dict[str, StrictBool] = Field(default_factory=dict)
    decision_brief: dict[str, str] = Field(default_factory=dict)
    strongest_objections: list[str] = Field(default_factory=list, max_length=3)


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
