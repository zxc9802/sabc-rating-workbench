"""Three-stage project decisions, versioned pilot plans and in-app follow-ups."""
from copy import deepcopy
from datetime import date, timedelta
from typing import Literal
from sabc.business_time import today

from pydantic import BaseModel, Field, ConfigDict, model_validator

from sabc.rating import DIMENSIONS, assess
from sabc.store import utcnow

STAGES = {'pre': '启动前', 'during': '试点中', 'post': '试点后'}


def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError('请填写有效日期，格式为 YYYY-MM-DD') from None


class Coverage(BaseModel):
    status: Literal['known', 'ask', 'unknown', 'external', 'future']
    reason: str = Field(min_length=1, max_length=1200)
    items: dict = Field(default_factory=dict)


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


def collection_gaps(life):
    from sabc.checkpoints import complete
    coverage = life.get('coverage', {})
    return [key for key in DIMENSIONS
            if coverage.get(key, {}).get('status') not in ('known', 'unknown', 'external', 'future')
            or not str(coverage.get(key, {}).get('reason', '')).strip()
            or not complete(coverage.get(key, {}).get('items', {}), key)]


def collection_ready(life):
    return bool(life.get('confirmed')) and not collection_gaps(life)


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
        if life.get('mode') != 'continuous' and review['conclusion'] not in allowed[life['stage']]:
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
    if result.get('pilot_plan') and (life.get('mode') == 'continuous' or life['stage'] in ('pre', 'during')):
        life['draft_plan'] = result['pilot_plan']
    project['lifecycle'] = life


def transition(project, action, body, company):
    life = state(project)
    on = today()
    reason = str(body.get('reason', '')).strip()
    if action == 'advance':
        if life['stage'] not in ('pre', 'during'):
            raise ValueError('已经处于试点后，请继续本阶段复盘')
        life.update(stage='during' if life['stage'] == 'pre' else 'post', confirmed=True,
                    paused=False, coverage={}, review=None, next_review_on=None)
    elif action == 'set_stage':
        stage = body.get('stage')
        if stage not in STAGES:
            raise ValueError('请选择实际项目阶段')
        if life.get('confirmed') and (life.get('actual_start') or life.get('plan')) and not reason:
            raise ValueError('修改已确认的阶段需要说明更正原因')
        life.update(stage=stage, confirmed=True, paused=False, coverage={}, review=None, draft_plan=None, next_review_on=None)
        if stage in ('during', 'post'):
            started = parse_date(body.get('actual_start', ''))
            if started > on:
                raise ValueError('实际开始日期不能在未来')
            life['actual_start'] = started.isoformat()
            if stage == 'post':
                ended = parse_date(body.get('actual_end', ''))
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
        started = parse_date(body.get('date', ''))
        if started > on:
            raise ValueError('实际开始日期不能在未来')
        life.update(stage='during', actual_start=started.isoformat(), paused=False, coverage={}, review=None)
        life['expected_end'] = (started + timedelta(days=life['plan']['duration_days'])).isoformat()
        life['next_review_on'] = (started + timedelta(days=life['plan']['checkin_after_days'])).isoformat()
    elif action == 'complete':
        if life['stage'] != 'during':
            raise ValueError('只有已经开始的试点可以结束')
        ended = parse_date(body.get('date', ''))
        if not date.fromisoformat(life['actual_start']) <= ended <= on:
            raise ValueError('实际结束日期须在开始日期之后且不晚于今天')
        if not reason:
            raise ValueError('请说明正常完成或提前停止的情况')
        life.update(stage='post', actual_end=ended.isoformat(), paused=False, coverage={}, review=None, next_review_on=on.isoformat())
    elif action == 'schedule':
        scheduled = parse_date(body.get('date', ''))
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


PROMPT = """
持续项目评估：不再划分启动前、试点中、试点后三个访谈阶段，不要求用户选择阶段、确认阶段或点击进入下一阶段。历史stage字段仅用于兼容旧记录，不限制当前提问或评价结论。
根据用户描述了解实际开展情况，再动态进行八维追问。尚未开展时问需求、价值路径、资源、预算和可承受的验证方式，不索要不存在的实际结果；已经执行时对照实际投入、效果、成本与原计划差异，不能以预测替代实际记录。不编造开始结束日期。
每轮JSON增加dimension_coverage，必须恰好覆盖strategy/market/return/resources/replication/cash/risk/opportunity。
每项为{"status":"known/ask/unknown/external/future","reason":"已知事实、推断及真正缺口"}。
known表示当前方向判断已有依据，不代表已验证；ask是用户尚可回答的关键问题；unknown仅限用户明确不知道；external需外部核查；future需实际执行验证。
每轮最多两个单一主题的问题；优先问影响当前决策的缺口，不重复询问已回答内容。用户说某一项不知道不能结束其他可答问题；用户确实无法提供或需要外部/未来验证时保留具体原因，不无限追问。
previous_stage_report字段携带最近一份历史报告，名称仅为兼容。结合历史判断、本轮回答和证据逐项重新梳理八维，保留仍适用事实，核对矛盾，不能照抄旧分数或把旧预测当验证结果。
仍有需要用户回答的问题时，questions必须列出该问题，对应维度标为ask，proposal与stage_review为null，直接继续交流，不宣称信息已完整。
普通问答只收集信息，proposal、stage_review、pilot_plan始终为null，不能预先生成评分草稿。八维无可答缺口且questions为空时，reply只写“信息已整理完成，现在生成报告吗？”，等待用户选择。
仅在本轮任务明确为生成报告时，基于已经收集的信息输出完整proposal与stage_review，不追加提问，不发起独立审查。无法补足的依据如实放入报告的未知项与验证任务。
stage_review结构为{conclusion,summary,next_action,next_review_days}，conclusion可为trial/adjust/not_recommended/needs_info/continue/pause/finish，根据实际情况给出建议而不是历史stage字段。
生成报告时的proposal包括八维判断、关键假设及验证任务、至少3条支持理由与3条反对理由。已知价值路径可作方向推断，basis=assumption并说明验证条件；真正无法判断则score=null、basis=unknown。不能因缺信息填零、强行平均或自动判C，也不能因用户不知道自动判B。评级由程序决定。
小规模验证必须有成立的价值路径、可承受的预算、最大损失与停止条件。已知不可解决的负面事实才支持否决；法律适用不清先外部核查，不默认违法。已核实否决项在proposal.vetoes关联已核验证据。
如关键依据确实无法补足，stage_review.conclusion=needs_info，summary第一句话必须以“暂缓评级：”开头，明确列出哪些关键依据无法补足、为何影响当前决策。区分用户明确不知道、需外部核查、需实际验证和信息尚未保存确认，不能把后者称为用户没提供。随后写已有判断、补证方式与恢复条件，不使用NR字母。
company未建立或未确认时先区分未提供与未保存确认：复用对话已有战略、现金、预算、人员，说明需要在公司资料核对保存；不能擅自确认公司基线或再次声称用户没有提供。
报告可包含试点建议，但不强制每个项目重新试点；已有结果时建议调整、继续或停止。pilot_plan为可选草稿，结构保持{objective,scope,method,metrics:[{name,baseline,target,measurement}],stop_conditions,owner,resources,cash_budget,internal_cost,max_loss,loss_estimate,planned_start,duration_days,checkin_after_days,records}。
metrics至少一项；四个金额是非负数；planned_start为日期或null；首次回访天数不能超过周期。未知关键预算、负责人先问，不编造事实或自动确认计划。可以建议数值但必须标明待确认。试点建议与下一步行动放入报告，reply简短衔接。
"""

PROMPT += """
借鉴结构化私董会的方法，以商业价值、执行资源、风险反方三个视角共同审视同一组八维事实。对外只有一个助手，不出现顾问名单、名人口吻或多人发言。
普通访谈不额外生成三份意见：在单轮内比较哪些缺口最可能改变决策、哪个问题当前可回答、是否已经问过，只输出最重要的一至两个问题。优先明确关键约束与可选方案，不为了搜集背景无限追问。
支持和反对理由必须针对具体事实、假设或待核查项，避免泛泛凑数；存在分歧时写清影响方向的关键变量和验证方法。不要以多视角意见一致提高证据等级。
普通问答一次完成八维信息整理与必要的风险追问，没有额外审查轮次。只有用户选择生成报告后才保存报告；讨论结果不自动授权投入，最终等级仍由现有八维权重、证据上限与否决规则计算。
"""
