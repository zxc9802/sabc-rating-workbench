"""Source-backed project classification, separate from the workbench lifecycle."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Framing(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_type: Literal['growth', 'internal', 'strategic', 'asset'] | None = None
    business_stage: Literal['unknown', 'idea', 'pilot', 'operating'] = 'unknown'
    purpose: Literal['unknown', 'new_project', 'continue', 'expand', 'research'] = 'unknown'
    quotes: dict[str, str] = Field(default_factory=dict)


def grounded(value, project, messages):
    if value is None:
        return None
    result = Framing.model_validate(value).model_dump()
    sources = [project.get('description', '')] + [m.get('content', '') for m in messages if m.get('role') == 'user']
    for field in ('project_type', 'business_stage', 'purpose'):
        quote = result['quotes'].get(field, '').strip()
        if result[field] not in (None, 'unknown') and (len(quote) < 4 or not any(quote in s for s in sources)):
            raise ValueError('项目类型、实际阶段及本次目的须对应用户原文，不得凭空确认')
    return result


def apply(project, value, messages):
    result = grounded(value, project, messages)
    if not result:
        return
    previous = project.get('framing', {})
    merged = {**previous, 'quotes': dict(previous.get('quotes', {}))}
    for field in ('project_type', 'business_stage', 'purpose'):
        if result[field] not in (None, 'unknown'):
            merged[field] = result[field]
            merged['quotes'][field] = result['quotes'][field]
    project['framing'] = merged
    if result.get('project_type'):
        project['project_type'] = result['project_type']
        project.setdefault('pending_patch', {}).pop('project_type', None)


PROMPT = '''
在第一轮问答内识别项目类型、真实经营阶段和本次评估目的，顶层增加framing对象：
{"project_type":"growth/internal/strategic/asset或null","business_stage":"unknown/idea/pilot/operating","purpose":"unknown/new_project/continue/expand/research","quotes":{"project_type":"用户连续原文","business_stage":"用户连续原文","purpose":"用户连续原文"}}。
商业增长是对外收费或获客，即使产品符合公司战略也不能据此改为战略能力；内部提效是本企业自己使用而改善成本/产能，产品帮助客户提效不代表本项目是内部项目。战略能力与重资产按实际价值与投入方式识别，不能根据含有AI字样分类。
真实经营阶段与工作台pre/during/post字段分开：已经商业化属于operating，不因外部整理者没有亲自试用就变成未试点。
外部资料整理、无权代表经营主体申请投资时优先purpose=research，即使研究主题是继续经营或增投；有经营授权时经营、增投、立项分别对应continue/expand/new_project。有经营收入不等于本次申请增投。
信息足够时直接识别，可用一句自然中文融入首轮回复，不额外要求用户选类型或逐项确认。不能确定的字段保留null/unknown，只在影响当前判断时用一个普通问题澄清。不得默认为商业增长。
后续明确纠正优先，更新framing并引用新的原话；没有新依据则沿用，不每轮重复分类。project_patch里的project_type必须与framing一致，不能私自另选。
评分、追问与行动须遵守已识别的类型和本次目的。公开资料研究可以列内部财务缺口，但不写成向外部整理者审批新项目或要求其替管理层授权。
'''
