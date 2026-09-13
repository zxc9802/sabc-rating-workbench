"""Deterministic V2 rating. This module never calls a model or network."""
from datetime import date
from sabc.business_time import today as business_today
import math

RULE_VERSION = 'SABC-2.1.0'
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


def known(value):
    return value is not None and str(value).strip() not in ('', '不知道', '未知', '待确认', '不清楚')


def missing_fields(project, company):
    missing = [label for key,label in PROJECT_FIELDS.items() if not known(project.get(key))]
    if project.get('project_type') not in TYPES: missing.append('有效的项目类型')
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
    missing=missing_fields(project,company)
    result={'rule_version':RULE_VERSION, 'grade':'NR', 'status':'待评级', 'base_score':None,
            'base_grade':None, 'evidence_level':'E0', 'confidence':'低', 'dimensions':[],
            'assumptions':[], 'triggered_rules':[], 'warnings':[], 'missing':missing,
            'action':ACTIONS['NR'], 'pros':proposal.get('pros',[]), 'cons':proposal.get('cons',[]),
            'resource_plan':{}, 'unique_sources':0,
            'validation_plan':[], 'reassessment_triggers':['公司战略、预算或团队变更','关键证据更新或过期','试验触及通过或止损阈值']}
    # A verified decisive blocker does not require filling unrelated fields first.
    by_id={item['id']:item for item in evidence}
    superseded={item['supersedes'] for item in evidence if item.get('supersedes')}
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
            continue
        if isinstance(score,bool) or not isinstance(score,(float,int)) or not math.isfinite(score) or not 0<=score<=5 or score*2 != int(score*2):
            raise ValueError(label+'原始分必须为0至5，步长0.5')
        if score < 3 and dim.get('basis') != 'fact':
            missing.append(label+'的低分需有已知负面事实，不能因缺资料扣分')
        result['dimensions'].append({'key':key,'name':label,'weight':weight,
            'score':score, 'weighted':round(score/5*weight,2),'reason':dim['reason'],
            'missing_evidence':dim.get('missing_evidence',''),
            'basis':dim.get('basis','assumption'),'evidence_ids':dim.get('evidence_ids',[])})
    assumptions=proposal.get('assumptions',[])
    if not assumptions: missing.append('至少一个决定项目成立的关键假设')
    if len([s for s in proposal.get('cons',[]) if s.strip()])<3: missing.append('至少3条反方审查意见')
    if len([s for s in proposal.get('pros',[]) if s.strip()])<3: missing.append('至少3条支持理由')
    if missing:
        result['missing']=list(dict.fromkeys(missing))
        result['validation_plan']=[{'claim':a['claim'],'method':a.get('validation_method') or '先确认资料来源和负责人',
            'pass':a.get('pass_threshold') or '待负责人确认通过条件',
            'fail':a.get('fail_threshold') or '条件未确认前暂停投入'} for a in assumptions]
        return result
    by_id={item['id']:item for item in evidence}
    superseded={item['supersedes'] for item in evidence if item.get('supersedes')}
    result['unique_sources']=len({item.get('canonical_source') or item.get('source_locator') for item in evidence})
    for assumption in assumptions:
        strengths=[]
        for eid in assumption.get('evidence_ids',[]):
            level,warnings=(0,['证据已有新版本，请核对并更新引用']) if eid in superseded else evidence_strength(by_id.get(eid,{}),today)
            strengths.append(level)
            result['warnings'].extend(f'{eid}：{w}' for w in warnings)
        level=max(strengths,default=0)
        result['assumptions'].append({**assumption,'level':f'E{level}'})
    level=min(int(a['level'][1]) for a in result['assumptions'])
    base_score=round(sum(d['weighted'] for d in result['dimensions']),2)
    base_index=3 if base_score>=90 else 2 if base_score>=75 else 1 if base_score>=60 else 0
    evidence_cap=[1,1,2,3][level]
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
        enough=all(dimensions[k]['score']>=4 for k in ('strategy','market','return','resources','replication'))
        if not enough or not all(gate.get(k) is True for k in ('repeatable','resources_available','portfolio_feasible','review_complete')):
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
