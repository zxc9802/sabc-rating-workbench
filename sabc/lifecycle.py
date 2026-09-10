"""Three-stage project decisions, versioned pilot plans and in-app follow-ups."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ConfigDict, model_validator

from sabc.rating import DIMENSIONS, assess
from sabc.store import utcnow

STAGES = {'pre': '启动前', 'during': '试点中', 'post': '试点后'}


def today():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date()


class Coverage(BaseModel):
    status: Literal['known', 'ask', 'unknown', 'external', 'future']
    reason: str = Field(min_length=1, max_length=1200)


class Metric(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    baseline: str = Field(min_length=1, max_length=500)
    target: str = Field(min_length=1, max_length=500)
    measurement: str = Field(min_length=1, max_length=1000)


class PilotPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    objective: str = Field(min_length=1, max_length=2000)
    scope: str = Field(min_length=1, max_length=2000)
    method: str = Field(min_length=1, max_length=3000)
    metrics: list[Metric] = Field(min_length=1, max_length=8)
    stop_conditions: str = Field(min_length=1, max_length=2000)
    owner: str = Field(min_length=1, max_length=500)
    resources: str = Field(min_length=1, max_length=2000)
    cash_budget: float = Field(ge=0, allow_inf_nan=False, strict=True)
    internal_cost: float = Field(ge=0, allow_inf_nan=False, strict=True)
    max_loss: float = Field(ge=0, allow_inf_nan=False, strict=True)
    loss_estimate: float = Field(ge=0, allow_inf_nan=False, strict=True)
    planned_start: date | None = None
    duration_days: int = Field(ge=1, le=365, strict=True)
    checkin_after_days: int = Field(ge=1, le=365, strict=True)
    records: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def interval(self):
        if self.checkin_after_days > self.duration_days:
            raise ValueError('首次回访不能晚于试点结束日期')
        return self


class StageReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conclusion: Literal['trial', 'adjust', 'not_recommended', 'needs_info', 'continue', 'pause', 'finish']
    summary: str = Field(min_length=1, max_length=4000)
    next_action: str = Field(min_length=1, max_length=2000)
    next_review_days: int | None = Field(default=None, ge=1, le=365, strict=True)


def initial(stage='pre', confirmed=True):
    return {'stage': stage, 'confirmed': confirmed, 'paused': False, 'coverage': {},
            'plan': None, 'draft_plan': None, 'plan_history': [], 'reviews': [], 'events': []}


def state(project):
    return deepcopy(project.get('lifecycle') or initial(confirmed=False))


def context(project):
    life = state(project)
    return {k: v for k, v in life.items() if k not in ('plan_history', 'events', 'reviews')} | {
        'recent_reviews': life['reviews'][-3:], 'today': today().isoformat(),
        'followup': followup(project)}


def followup(project, on=None):
    life = state(project)
    if not life['confirmed'] or life['paused']:
        return None
    due = life.get('next_review_on')
    if not due:
        return None
    return {'date': due, 'due': due <= (on or today()).isoformat(),
            'kind': 'start' if life['stage'] == 'pre' else 'completion' if life['stage'] == 'during' and due >= (life.get('expected_end') or due) else 'review'}


def check_budget(plan, company):
    required = ('budget', 'cash_available', 'cash_safety_line')
    if not company.get('confirmed') or any(not isinstance(company.get(k), (int, float)) or isinstance(company[k], bool) for k in required):
        raise ValueError('请先确认公司预算、可用现金和现金安全线')
    available = max(0, min(company['budget'], company['cash_available'] - company['cash_safety_line']))
    if plan['cash_budget'] > available:
        raise ValueError('试点现金预算超过当前可用资金，请先调整方案')
    if plan['loss_estimate'] > plan['max_loss']:
        raise ValueError('估计不可收回的损失超过承受上限，请先调整方案')


def absorb(project, result, company, evidence):
    life = state(project)
    coverage = result.get('dimension_coverage') or {}
    if coverage:
        if set(coverage) != set(DIMENSIONS):
            raise ValueError('阶段分析必须覆盖八个维度')
        life['coverage'] = coverage
    review = result.get('stage_review')
    if not life['confirmed']:
        project['lifecycle'] = life
        return
    if review:
        allowed = {'pre': {'trial', 'adjust', 'not_recommended', 'needs_info'},
                   'during': {'continue', 'adjust', 'pause', 'finish', 'needs_info'},
                   'post': {'continue', 'adjust', 'not_recommended', 'needs_info'}}
        if review['conclusion'] not in allowed[life['stage']]:
            raise ValueError('评价结论与实际项目阶段不符')
        proposal = result.get('proposal') or {}
        hard_stop = assess(project, company, evidence, proposal).get('hard_stop', False)
        covered = life.get('coverage', {})
        missing = set(covered) != set(DIMENSIONS) or any(v['status'] == 'ask' for v in covered.values())
        # A missing interview answer is not a negative business fact or an approval.
        if missing and not hard_stop and review['conclusion'] in ('trial', 'not_recommended', 'continue', 'finish'):
            review = {**review, 'conclusion': 'needs_info', 'next_action': '继续补充仍会改变判断的关键问题。'}
        if hard_stop:
            review = {**review, 'conclusion': 'not_recommended' if life['stage'] != 'during' else 'pause',
                      'next_action': '已核实的决定性障碍尚未解除，当前方案不建议继续投入。'}
        life['review'] = {**review, 'stage': life['stage'], 'time': utcnow(),
                          'plan_version': (life.get('plan') or {}).get('version'), 'coverage': deepcopy(covered)}
        life['reviews'].append(life['review'])
    if result.get('pilot_plan') and life['stage'] in ('pre', 'during'):
        life['draft_plan'] = result['pilot_plan']
    project['lifecycle'] = life


def transition(project, action, body, company):
    life = state(project)
    on = today()
    reason = str(body.get('reason', '')).strip()
    if action == 'set_stage':
        stage = body.get('stage')
        if stage not in STAGES:
            raise ValueError('请选择实际项目阶段')
        if life.get('confirmed') and (life.get('actual_start') or life.get('plan')) and not reason:
            raise ValueError('修改已确认的阶段需要说明更正原因')
        life.update(stage=stage, confirmed=True, paused=False, coverage={}, review=None, draft_plan=None, next_review_on=None)
        if stage in ('during', 'post'):
            started = date.fromisoformat(body.get('actual_start', ''))
            if started > on:
                raise ValueError('实际开始日期不能在未来')
            life['actual_start'] = started.isoformat()
            if stage == 'post':
                ended = date.fromisoformat(body.get('actual_end', ''))
                if not started <= ended <= on:
                    raise ValueError('实际结束日期须在开始日期之后且不晚于今天')
                life['actual_end'] = ended.isoformat()
                life['next_review_on'] = on.isoformat()
            else:
                life['actual_end'] = None
                life['next_review_on'] = on.isoformat()
        else:
            life.update(actual_start=None, actual_end=None, expected_end=None, plan=None)
    elif action == 'confirm_plan':
        if life['stage'] == 'post' or not life['confirmed']:
            raise ValueError('请先确认启动前或试点中的实际阶段')
        if (life.get('review') or {}).get('conclusion') not in ('trial', 'continue', 'adjust'):
            raise ValueError('请先完成初步评价，确认项目适合试点或可调整后试点')
        if any(v['status'] == 'ask' for v in life.get('coverage', {}).values()):
            raise ValueError('请先补充当前仍可回答的关键问题，再确认试点方案')
        if life.get('plan') and not reason:
            raise ValueError('调整已确认的试点方案需要说明原因')
        plan = PilotPlan.model_validate(body.get('plan')).model_dump(mode='json')
        check_budget(plan, company)
        plan.update(version=len(life['plan_history']) + 1, confirmed_at=utcnow(), change_reason=reason)
        life['plan_history'].append(deepcopy(plan))
        life.update(plan=plan, draft_plan=None)
        if life['stage'] == 'pre':
            life['next_review_on'] = plan['planned_start']
        else:
            life['expected_end'] = (date.fromisoformat(life['actual_start']) + timedelta(days=plan['duration_days'])).isoformat()
            life['next_review_on'] = min(life['expected_end'], (on + timedelta(days=plan['checkin_after_days'])).isoformat())
    elif action == 'start':
        if life['stage'] != 'pre' or not life.get('plan') or not life['confirmed']:
            raise ValueError('请先确认启动前评价和试点方案')
        if (life.get('review') or {}).get('conclusion') not in ('trial', 'adjust'):
            raise ValueError('当前评价尚不支持启动，请先处理关键障碍')
        check_budget(life['plan'], company)
        started = date.fromisoformat(body.get('date', ''))
        if started > on:
            raise ValueError('实际开始日期不能在未来')
        life.update(stage='during', actual_start=started.isoformat(), paused=False, coverage={}, review=None)
        life['expected_end'] = (started + timedelta(days=life['plan']['duration_days'])).isoformat()
        life['next_review_on'] = (started + timedelta(days=life['plan']['checkin_after_days'])).isoformat()
    elif action == 'complete':
        if life['stage'] != 'during':
            raise ValueError('只有已经开始的试点可以结束')
        ended = date.fromisoformat(body.get('date', ''))
        if not date.fromisoformat(life['actual_start']) <= ended <= on:
            raise ValueError('实际结束日期须在开始日期之后且不晚于今天')
        if not reason:
            raise ValueError('请说明正常完成或提前停止的情况')
        life.update(stage='post', actual_end=ended.isoformat(), paused=False, coverage={}, review=None, next_review_on=on.isoformat())
    elif action == 'schedule':
        scheduled = date.fromisoformat(body.get('date', ''))
        if scheduled < on or not reason:
            raise ValueError('请选择今天或以后的回访日期，并说明安排原因')
        life['next_review_on'] = scheduled.isoformat()
    elif action in ('pause', 'resume'):
        if not reason:
            raise ValueError('请说明暂停或恢复原因')
        life['paused'] = action == 'pause'
        if action == 'resume':
            life['next_review_on'] = on.isoformat()
    else:
        raise ValueError('未知阶段操作')
    life['events'].append({'action': action, 'reason': reason, 'time': utcnow(), 'stage': life['stage']})
    return {**project, 'lifecycle': life, 'version': project['version'] + 1}


PROMPT = '''
三阶段规则优先于统一评分收口要求。实际阶段由project.lifecycle提供，只有用户通过阶段操作确认后才能切换，模型不能修改阶段或日期。
confirmed=false时，先问项目尚未启动、正在试点还是已完成，并提示在阶段栏确认；不能从“4周”等周期或历史模拟描述推断已发生结果。
每轮JSON增加dimension_coverage，必须恰好覆盖strategy/market/return/resources/replication/cash/risk/opportunity。
每项为{"status":"known/ask/unknown/external/future","reason":"简短记住已知事实、推断及真正缺口"}。
known表示当期方向判断已有依据，不代表效果已验证；ask只用于用户尚可回答的关键问题；unknown是用户明确不知道，external需外部核查，future需未来执行。
这些记录跨轮保留，不因最近对话截断丢失事实。每阶段都检查八维，已知不重复问，优先处理当前可答缺口。每轮最多两个单一主题的问题，不把五六个子问题塞进两个问号。
启动前pre：给出项目初评，再决定是否值得试点。只问现状、痛点、价值路径、可用资源、风险和替代方案，不索要尚不存在的试点结果；预计收益和目标不是实际效果。未来结果纳入验证任务，不用它阻止初评。
试点中during：先读取已确认plan和已上传记录，对照目标、投入、数据质量、停止条件，只追问实际已发生的变化；不能因日期到期或前几天改善就宣布完成或成功。
试点后post：先汇总实际记录并与原计划比较，必要时补问差异、完整成本、持续性、复用条件，然后给proposal由程序算综合评分。缺证据不得伪造，提前停止也可以复盘。
在当期可回答的关键缺口解决后，可输出stage_review：{"conclusion":"结论代码","summary":"具体初评/阶段评价，指出优势风险及未知，不能只说可以试","next_action":"下一步具体行动","next_review_days":建议多少天后回访或null}。
pre结论为trial值得试点/adjust调整后再试/not_recommended当前不适合/needs_info补关键资料；during为continue/adjust/pause/finish建议结束并复盘/needs_info；post为continue/adjust/not_recommended/needs_info。
八维有ask时继续提问；只有已核验的决定性否决条件可以提前结束。未取得资料、尚未验证、用户不知道不等于负面事实，不能据此拒绝项目。
明确违法、无法取得且无替代的关键资源、不可承受且无法缩小的最低投入/损失、已证实的不可持续价值结构可以否决当前方案；必须在proposal.vetoes关联已核验资料。法律适用不清先查官方依据，不默认违法。否决说明当前条件和恢复条件。
pre或during可输出pilot_plan草稿，未知关键预算或负责人先问；可提出建议数值但明确待用户确认，不能写入project_patch作为事实。
pilot_plan结构为{objective,scope,method,metrics:[{name,baseline,target,measurement}],stop_conditions,owner,resources,cash_budget,internal_cost,max_loss,loss_estimate,planned_start,duration_days,checkin_after_days,records}。
文本字段用中文具体填写；metrics至少一项；baseline未知则写补测方法；四个金额为非负数字，分别是现金预算、内部工时折算、最大可承受损失、估计不可收回损失；不能把现金和工时混为一谈。planned_start为YYYY-MM-DD或null；天数为整数，首次回访不晚于试点结束。records说明保存哪些记录。
草稿要与评价发现的关键假设一一对应。用户不会设计时先建议，不让用户完成所有设计；无需为了试点而要求用户提供未来结果。方案确认、实际启动、结束以及回访日期变更都由用户操作，不在正文声称已经替用户完成。
仅输出与本轮相关的stage_review/pilot_plan，否则为null。pre和during的阶段评价不要求proposal中八维全部给数值，也不受“至少3条正反理由”等最终报告完整度约束。post仍遵守最终评分约束。不生成最终等级，详细阶段评价和方案会在独立面板显示。
'''
