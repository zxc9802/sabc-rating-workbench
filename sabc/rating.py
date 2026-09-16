"""Deterministic V2 rating. This module never calls a model or network."""
from datetime import date
from sabc.business_time import today as business_today
import math

RULE_VERSION = 'SABC-2.2.0'
DIMENSIONS = {
    'strategy': ('战略匹配度', 15), 'market': ('市场空间 / 需求价值', 15),
    'return': ('经营回报确定性', 20), 'resources': ('资源匹配 / 凭什么赢', 15),
    'replication': ('可复制性与复利资产', 10), 'cash': ('现金流与资金效率', 10),
    'risk': ('风险可控性', 10), 'opportunity': ('机会成本', 5),
}
TYPES = {'growth': '商业增长', 'internal': '内部AI / 提效', 'strategic': '战略能力 / 资产', 'asset': '重资产 / 扩张'}
PROJECT_FIELDS = {'name':'项目名称', 'project_type':'项目类型', 'target_user':'目标客户或内部用户',
                  'business_goal':'经营目标', 'value_mechanism':'收益或价值兑现机制',
                  'success_metric':'成功指标', 'timeframe':'验证周期', 'risks':'主要风险'}
GRADES = ['C', 'B', 'A', 'S']
ACTIONS = {'S':'集中资源，分阶段放大', 'A':'正式立项，分阶段投入',
           'B':'小规模验证，禁止重仓', 'C':'当前不立项', 'NR':'补齐信息后再评级'}
GRADE_THRESHOLDS = {'S': 90, 'A': 75, 'B': 60}
EVIDENCE_CAPS = (1, 1, 2, 3)
S_DIMENSIONS = ('strategy', 'market', 'return', 'resources', 'replication')
S_CONDITIONS = ('repeatable', 'resources_available', 'portfolio_feasible', 'review_complete')


def upgrade_requirements():
    return {
        'upgrade_a': f'需要通过本项目的小规模试点或其他可直接适用的验证，取得已核验的结果，支持各项关键假设（证据达到E2或以上）。同时，业务总分须至少{GRADE_THRESHOLDS["A"]}分，无一票否决或只能小规模验证的限制，投入也须在可用资源范围内。满足证据要求不代表自动升为A级，仍须综合上述条件重新评估。',
        'upgrade_s': f'需要用多个周期或样本的重复验证结果，支持各项关键假设（证据达到E3）。同时，业务总分须至少{GRADE_THRESHOLDS["S"]}分，' + '、'.join(DIMENSIONS[k][0] for k in S_DIMENSIONS)
                     + '这五维的原始分均须至少4分；核心资源可获得，机会成本与资源组合合理，主要风险及反对意见已审查，且无否决或评级上限限制，才具备集中资源投入的条件。重复验证可以在同一项目内完成，不强制新增区域或产品。',
    }


def known(value):
    return value is not None and str(value).strip() not in ('', '不知道', '未知', '待确认', '不清楚')


def missing_fields(project, company, assessment_scope=None):
    missing = [label for key,label in PROJECT_FIELDS.items() if not known(project.get(key))]
    if project.get('project_type') not in TYPES: missing.append('有效的项目类型')
    if project.get('framing', {}).get('purpose') == 'research' and not (assessment_scope or {}).get('company_baseline'):
        # The account owner is not the operator of a publicly researched business.
        missing.append('被研究业务的可用资源、现金安全线及投入授权尚不能由账号公司基线确认')
        return list(dict.fromkeys(missing))
    for key,label in {'strategy':'公司当前战略', 'team':'可调用人员', 'budget':'新项目可用预算',
                      'cash_available':'可用现金', 'cash_safety_line':'现金安全线'}.items():
        if not known(company.get(key)): missing.append(label)
    if not company.get('confirmed'): missing.append('负责人确认公司基线')
    if not known(project.get('budget_requested')): missing.append('首期投入范围')
    return list(dict.fromkeys(missing))


def evidence_strength(item, today):
    warnings=[]
    if not item.get('source_locator') or not item.get('data_period'):
        return 0, ['证据缺少来源或数据期间']
    if item.get('verification_status') != 'verified':
        return 0, ['证据尚未核验']
    try:
        level=int(item.get('level',0))
        if level not in range(4): raise ValueError()
        expires=date.fromisoformat(item['valid_until']) if item.get('valid_until') else None
    except (ValueError,TypeError):
        return 0, ['证据等级或有效日期无效']
    if expires and expires < today:
        level=min(level,1)
        warnings.append('证据已过期，需重新核验')
    if item.get('conflict'): level=min(level,1); warnings.append('存在尚未解释的冲突证据')
    if item.get('source_type') not in ('internal','experiment','transfer_reviewed'): level=min(level,1)
    if level >= 2 and not item.get('scope'): level=1; warnings.append('缺少直接适用范围')
    if level == 3 and not item.get('repeat_verified'): level=2
    return level,warnings


def assess(project, company, evidence, proposal, today=None):
    today=today or business_today()
    missing=missing_fields(project,company,proposal.get('assessment_scope'))
    result={'rule_version':RULE_VERSION, 'grade':'NR', 'status':'待评级', 'base_score':None,
            'base_grade':None, 'evidence_level':'E0', 'confidence':'低', 'dimensions':[],
            'assumptions':[], 'triggered_rules':[], 'warnings':[], 'missing':missing,
            'action':ACTIONS['NR'], 'pros':proposal.get('pros',[]), 'cons':proposal.get('cons',[]),
            'resource_plan':{}, 'unique_sources':0, 'evidence_evaluated':False,
            'upgrade_requirements':upgrade_requirements(),
            'validation_plan':[], 'reassessment_triggers':['公司战略、预算或团队变更','关键证据更新或过期','试验触及通过或止损阈值']}
    # A verified decisive blocker does not require filling unrelated fields first.
    by_id={item['id']:item for item in evidence}
    superseded={item['supersedes'] for item in evidence if item.get('supersedes')}
    active=[item for item in evidence if item['id'] not in superseded]
    result['unique_sources']=len({item.get('canonical_source') or item.get('source_locator') or item['id'] for item in active})
    result['evidence_count']=len(active)
    publishers={str(item['publisher']).strip() for item in active if item.get('publisher')}
    result['publisher_count']=len(publishers) if active and all(item.get('publisher') for item in active) else None
    strengths={item['id']:evidence_strength(item,today) for item in active}
    for item in active:
        result['warnings'].extend(f'{item.get("title") or "资料"}：{w}' for w in strengths[item['id']][1])
    assumptions=proposal.get('assumptions',[])
    for assumption in assumptions:
        levels=[]
        for eid in assumption.get('evidence_ids',[]):
            strength,warnings=strengths.get(eid,(0,['证据已有新版本或引用不存在，请核对并更新引用']))
            levels.append(strength)
            if eid not in strengths: result['warnings'].extend(warnings)
        result['assumptions'].append({**assumption,'level':f'E{max(levels,default=0)}'})
    level=min((int(a['level'][1]) for a in result['assumptions']),default=0)
    result.update(evidence_level=f'E{level}',evidence_evaluated=True)
    blockers=[v['reason'] for v in proposal.get('vetoes',[]) if v.get('confirmed') and v.get('evidence_ids')
              and all(eid in by_id and eid not in superseded
                      and by_id[eid].get('verification_status')=='verified'
                      and not by_id[eid].get('conflict')
                      and (not by_id[eid].get('valid_until') or by_id[eid]['valid_until']>=today.isoformat())
                      for eid in v['evidence_ids'])]
    if blockers:
        result.update(grade='C',status='当前方案不建议继续',action='当前方案不适合做，先解除决定性障碍',
                      hard_stop=True,triggered_rules=['一票否决：'+reason for reason in blockers],
                      missing=[],warnings=['其他维度尚未完成不影响本次否决；不代表已经全面验证项目。'])
        return result
    dimensions=proposal.get('dimensions',{})
    for key,(label,weight) in DIMENSIONS.items():
        dim=dimensions.get(key,{})
        score=dim.get('score')
        if score is None or dim.get('basis') == 'unknown' or not dim.get('reason'):
            missing.append(label+'的方向性判断')
            result['dimensions'].append({'key':key,'name':label,'weight':weight,'score':None,'weighted':None,
                'reason':dim.get('reason') or '现有依据不足以形成该维判断', 'basis':'unknown',
                'missing_evidence':dim.get('missing_evidence') or '需补充支持该维判断的具体依据',
                'evidence_ids':dim.get('evidence_ids',[])})
            continue
        if isinstance(score,bool) or not isinstance(score,(float,int)) or not math.isfinite(score) or not 0<=score<=5 or score*2 != int(score*2):
            raise ValueError(label+'原始分必须为0至5，步长0.5')
        if score < 3 and dim.get('basis') != 'fact':
            missing.append(label+'的低分需有已知负面事实，不能因缺资料扣分')
        result['dimensions'].append({'key':key,'name':label,'weight':weight,
            'score':score, 'weighted':round(score/5*weight,2),'reason':dim['reason'],
            'missing_evidence':dim.get('missing_evidence',''),
            'basis':dim.get('basis','assumption'),'evidence_ids':dim.get('evidence_ids',[])})
    if not assumptions: missing.append('至少一个决定项目成立的关键假设')
    if len([s for s in proposal.get('cons',[]) if s.strip()])<3: missing.append('至少3条反方审查意见')
    if len([s for s in proposal.get('pros',[]) if s.strip()])<3: missing.append('至少3条支持理由')
    if missing:
        result['missing']=list(dict.fromkeys(missing))
        result['validation_plan']=[{'claim':a['claim'],'method':a.get('validation_method') or '先确认资料来源和负责人',
            'pass':a.get('pass_threshold') or '待负责人确认通过条件',
            'fail':a.get('fail_threshold') or '条件未确认前暂停投入'} for a in assumptions]
        return result
    base_score=round(sum(d['weighted'] for d in result['dimensions']),2)
    base_index=next((GRADES.index(g) for g,t in GRADE_THRESHOLDS.items() if base_score>=t),0)
    evidence_cap=EVIDENCE_CAPS[level]
    candidate=min(base_index,evidence_cap)
    rules=[f'证据等级 E{level}，最高 {GRADES[evidence_cap]} 级']
    if proposal.get('policy_caps'):
        candidate=min(candidate,1)
        rules.extend('B级封顶：'+str(reason) for reason in proposal['policy_caps'])
    for veto in proposal.get('vetoes',[]):
        refs=veto.get('evidence_ids',[])
        if veto.get('confirmed') and refs and all(eid in by_id and eid not in superseded and by_id[eid].get('verification_status')=='verified' and not by_id[eid].get('conflict') and (not by_id[eid].get('valid_until') or by_id[eid]['valid_until']>=today.isoformat()) for eid in refs):
            candidate=0; rules.append('一票否决：'+veto['reason'])
        else:
            result['warnings'].append('待核验红线：'+veto.get('reason','未说明'))
            candidate=min(candidate,1)
    for field in ('budget','cash_available','cash_safety_line'):
        if isinstance(company[field],bool) or not isinstance(company[field],(int,float)) or not math.isfinite(company[field]) or company[field]<0:
            raise ValueError('公司预算和现金必须为非负有限数字')
    requested=project['budget_requested']
    if isinstance(requested,bool) or not isinstance(requested,(int,float)) or not math.isfinite(requested) or requested<0:
        raise ValueError('首期投入必须为非负有限数字')
    available=max(0,min(company['budget'],company['cash_available']-company['cash_safety_line']))
    if requested>available:
        candidate=min(candidate,1)
        rules.append('首期投入超过当前可用资源，需要调整方案或确认不可获得')
    if candidate==3:
        gate=proposal.get('s_conditions',{})
        enough=all(dimensions[k]['score']>=4 for k in S_DIMENSIONS)
        if not enough or not all(gate.get(k) is True for k in S_CONDITIONS):
            candidate=2; rules.append('S级准入条件未全部满足')
    grade=GRADES[candidate]
    result.update(grade=grade, status='暂定评级' if level<2 else '正式评级',
                  base_score=base_score,base_grade=GRADES[base_index],evidence_level=f'E{level}',
                  confidence='低' if level==0 else '中' if level<3 or result['warnings'] else '高',
                  triggered_rules=rules,action=ACTIONS[grade])
    if requested>available and grade=='B':
        result['action']='暂缓投入，先调整投入与验证方案'
    result['resource_plan']={'available_limit':available,
        'formula':'min(新项目预算, 可用现金 - 现金安全线)，最低为0',
        'proposed_budget':requested if requested<=available and grade in ('A','S') else None,
        'note':'B级需先按关键假设拆解最小验证成本，再由负责人批准。' if grade=='B' else
               'C级不建议新增投入。' if grade=='C' else '金额引用项目申报值，不代表自动批准；人员与周期需负责人确认。'}
    result['validation_plan']=[{'claim':a['claim'], 'pass':a.get('pass_threshold') or '待定义可量化通过阈值',
        'fail':a.get('fail_threshold') or '待定义失败与止损阈值',
        'method':a.get('validation_method') or '补充本项目真实试验记录'}
        for a in sorted(result['assumptions'],key=lambda a:a['level'])[:2]]
    result['warnings']=list(dict.fromkeys(result['warnings']))
    return result
