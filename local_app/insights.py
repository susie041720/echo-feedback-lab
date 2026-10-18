"""Focused, evidence-linked editorial findings. No model inference or category-wide votes."""
import hashlib,json,math,re
from pathlib import Path
import evidence
CORE_CONFIG=json.loads((Path(__file__).parent/'config/core_findings.json').read_text())
VERSION='findings-5.2-concise-titles'
# Compatibility only: recommendations are selected by concrete themes below.
DIRECTIONS={}

def canonical(key):return key[7:] if key.startswith('custom:') else key

def ids(sources):return sorted({s['review_id'] for s in sources})

def policy(group):
    key=canonical(group['theme_key']);base=CORE_CONFIG.get('theme_actions',{}).get(key,{})
    label=base.get('negative_label',base.get('label',group['summary'])) if group['polarity']=='槽点' else base.get('label',group['summary'])
    if key=='operating-noise' and group['polarity']=='优点':label='运行声音低于预期' if all((s.get('comparison') or evidence.comparison(s))['basis']=='相对于预期' for s in group['sources']) else '运行声音体验'
    return dict(base,label=label)

def family(group):
    key=canonical(group['theme_key'])
    for name,definition in CORE_CONFIG['clusters'].items():
        if group['polarity']!=definition['polarity'] or key not in definition['theme_keys']:continue
        condition=definition.get('member_conditions',{}).get(key)
        if condition and not all(re.search(condition['evidence_regex'],s['evidence'],re.I) for s in group['sources']):continue
        return name
    return None

def group_id(category,group):return '|'.join([category,group['theme_key'],group['bucket'],group['polarity']])

def group_action(group):
    p=policy(group);positive=group['polarity']=='优点';label=p['label']
    if positive:
        return {'action':p.get('positive_action','保留这条反馈所认可的“'+label+'”体验，不扩大适用范围。'),'basis':'评论直接表达了对“'+label+'”的认可。','missing':None,'validation':None}
    return {'action':p.get('negative_action','先确认“'+label+'”所指的具体表现和发生条件，再决定是否需要改进。'),'basis':'原文明确描述“'+label+'”，支持针对该问题了解条件，不支持按整个大类归因。','missing':p.get('missing','缺少该问题的具体发生条件与复现证据。'),'validation':'取得相应条件后对照原文所述现象，记录能否复现。'}

def build(agg,run,raw_total,raw_reviews=None):
    raw_reviews=raw_reviews or {};den=agg['analyzed_count'];entries=[];theme_actions={}
    for category in agg['categories']:
        for group in category['groups']:
            if group['bucket']=='actual' and group['polarity'] in ['优点','槽点']:
                entries.append((category,group));theme_actions[group_id(category['key'],group)]=group_action(group)
            elif group['bucket'] in ['concern','unknown'] and group['polarity']=='槽点':entries.append((category,group))
    comparable=set(CORE_CONFIG.get('comparable_specific_themes',[]));opposites={}
    for c,g in entries:
        if g['bucket']=='actual':opposites.setdefault((c['key'],canonical(g['theme_key'])),set()).add(g['polarity'])
    shared={key for key,ps in opposites.items() if ps=={'优点','槽点'} and key[1] in comparable}
    merged={}
    for c,g in entries:
        theme=canonical(g['theme_key']);cluster=family(g) if g['bucket']=='actual' else None
        if (c['key'],theme) in shared and g['bucket']=='actual':key=('comparison',c['key'],theme)
        elif g['bucket']!='actual':key=('pending',c['key'],theme)
        elif cluster:key=('cluster',cluster,g['polarity'])
        else:key=('theme',c['key'],theme,g['polarity'])
        f=merged.setdefault(key,{'groups':[],'sources':[],'category_keys':[],'category_names':[],'family':cluster or theme})
        f['groups'].append(g);f['sources'].extend(g['sources'])
        if c['key'] not in f['category_keys']:f['category_keys'].append(c['key']);f['category_names'].append(c['name'])
    findings=[]
    for key,f in merged.items():
        f['sources']=list({(s['review_id'],s['aspect_id']):s for s in f['sources']}.values())
        pos=[s for s in f['sources'] if s['bucket']=='actual' and s['polarity']=='优点'];neg=[s for s in f['sources'] if s['bucket']=='actual' and s['polarity']=='槽点'];pending=[s for s in f['sources'] if s['bucket']!='actual']
        hazards=evidence.safety_concern(pending);links=evidence.behavior_links(f['sources'],agg['behaviors'],raw_reviews)
        causal_returns=[b for b in links if b['actual_return'] and b['association']=='原文明示退货原因']
        if pending and not hazards and not causal_returns:continue
        f.update(id=hashlib.sha256(repr(key).encode()).hexdigest()[:16],category_key=f['category_keys'][0],category=' · '.join(f['category_names']),themes=list(dict.fromkeys(g['summary'] for g in f['groups'])),review_ids=ids(f['sources']),positive_review_ids=ids(pos),negative_review_ids=ids(neg),pending_review_ids=ids(pending),denominator=den,behavior_links=links,counterpoints=[])
        f.update(count=len(f['review_ids']),positive_count=len(f['positive_review_ids']),negative_count=len(f['negative_review_ids']),pending_count=len(f['pending_review_ids']))
        f['support_label']='个别反馈' if f['count']==1 else str(f['count'])+' 条评论';f['polarity']='槽点' if neg or pending else '优点'
        definition=CORE_CONFIG['clusters'].get(f['family'],{}) if key[0]=='cluster' else {}
        label=definition.get('label',policy(f['groups'][0])['label'])
        f['conditions']=list(dict.fromkeys(s['scenario'] for s in f['sources'] if s.get('scenario') and s['scenario']!='未说明'))
        f['contributions']=[{'theme_key':g['theme_key'],'label':CORE_CONFIG['clusters'].get(f['family'],{}).get('member_conditions',{}).get(canonical(g['theme_key']),{}).get('label',policy(g)['label']),'count':len(set(g['review_ids'])),'review_ids':g['review_ids'],'bucket':g['bucket'],'polarity':g['polarity']} for g in f['groups']]
        f['contributions'].sort(key=lambda c:-c['count'])
        f['has_evaluation_difference']=key[0]=='comparison';f['difference_theme_keys']=[key[-1]] if key[0]=='comparison' else []
        f['difference_note']='同一具体主题存在不同评价；比较依据与使用条件分别保留，差异原因未知，不能相减或认定事实矛盾。' if key[0]=='comparison' else ''
        f['comparison_bases']=[]
        for basis in dict.fromkeys((s.get('comparison') or evidence.comparison(s))['basis'] for s in f['sources']):
            sources=[s for s in f['sources'] if (s.get('comparison') or evidence.comparison(s))['basis']==basis]
            f['comparison_bases'].append({'basis':basis,'count':len(ids(sources)),'review_ids':ids(sources),'sources':sources})
        n=f['count'];concentrated=n>=max(2,math.ceil(den*CORE_CONFIG['selection']['positive_min_fraction']))
        critical=None;missing=[]
        if pending:
            safety_topic=policy(f['groups'][0]).get('safety_topic','“'+label+'”相关的')
            f['title']=('一条评论' if n==1 else str(n)+'条评论')+('因'+safety_topic+'安全担忧而退货，需先核实' if causal_returns else '表达'+safety_topic+'安全担忧，需先核实')
            concern=next((s for s in pending if s['bucket']=='concern'),pending[0]);f['explanation']=concern['claim']+(' 作者表示已退货，原文明示与该担忧相关。' if causal_returns else '')
            action='核对原文明示的工作状态与保护机制，并回访是否实际观察到异常；再决定是否需要进一步测试或产品调整。'
            basis='原文有具体安全担忧'+('及明确相关的退货自述。' if causal_returns else '。');critical='尚未证实事故、缺陷或所担忧的后果；不能由担忧推断发生率。';missing=['缺少实际观察、保护机制说明与正常条件下的核查证据。'];validation='核查实际工作状态、保护机制说明和原文所述条件，记录是否可复现。';tier='优先核实安全担忧';impact='安全担忧尚未核实'+('；有明确相关的退货自述' if causal_returns else '')
        elif key[0]=='comparison':
            label=CORE_CONFIG.get('theme_actions',{}).get(canonical(f['groups'][0]['theme_key']),{}).get('comparison_label',f['groups'][0]['summary'])
            f['title']=label+'的评价存在差异，需结合各自条件理解';f['explanation']=f'{f["positive_count"]}条评论认可：'+pos[0]['claim'].split('。')[0]+'。'+f'{f["negative_count"]}条评论提出负面体验：'+neg[0]['claim'].split('。')[0]+'。比较依据及条件分别保留，差异原因未知。'
            action='分别核对双方对“'+label+'”的评价对象、比较基准和原文明示的条件，再比较同口径体验。';basis='双方引文都指向同一具体主题；现有正负数量不能解释差异原因。';critical='比较条件尚未统一，差异原因未知。';missing=['缺少双方可按同一口径比较的条件。'];validation='对照同一对象、阶段和使用条件；不把不同基准的评价判为矛盾。';tier='针对场景调查';impact='同一具体主题存在不同体验'
        else:
            qualifier='一条评论' if n==1 else str(n)+'条评论'
            f['title']=label if pos else qualifier+'反映'+label
            # A one-member overcooking cluster cannot claim both burning and dryness.
            if f['family']=='overcooking' and len(f['groups'])==1:f['title']=qualifier+'反映'+f['contributions'][0]['label']
            if len(f['groups'])>1:
                f['explanation']='；'.join(str(c['count'])+'条提到'+c['label'] for c in f['contributions'][:3])+'。'
                if neg:f['explanation']=' '.join(g['sources'][0]['claim'] for g in f['groups'])
            elif n>1:f['explanation']=f['groups'][0]['description'].split('涉及情境：')[0]
            else:f['explanation']=f['sources'][0]['claim']
            if n==1 and not any(word in f['explanation'] for word in ['问题不大','不确定','无法','未说明']):critical='仅一条评论支持，尚不能判断出现范围。'
            if f['conditions'] and len(f['groups'])==1 and n==1:f['explanation']+=' 涉及：'+'；'.join(c.rstrip('。') for c in f['conditions'][:2])+'。'
            p=policy(f['groups'][0]);a=group_action(f['groups'][0])
            action=definition.get('action',a['action']);basis=definition.get('action_basis',a['basis']);validation=a['validation'] if neg else None
            if neg:missing=[definition.get('missing',a['missing'])]
            if neg and f['family']=='overcooking':
                validation='用各条评论各自的食材与参数复测，分别记录顶部焦糊、整体过干或烹饪过度。'
                if any('不确定' in s['claim'] or '不能确定' in s['claim'] for s in neg):critical='顶部焦糊与闭合异常是否有关尚未证实，应分别核查。'
            if neg and f['family']=='startup-noise':critical='评论者明确不确定是否正常；比较对象与声音参考尚未提供。'
            if neg and f['family']=='time-temp-learning':critical='评论者认为问题不大，且“可能失败”不证明失败已经发生。'
            if neg and f['family']=='basket-design':critical='这是个人结构偏好，原文未证明部件故障。'
            if neg and f['family']=='cooking-fit':critical='具体不适配原因未说明，不能推断为容量或功能缺失。'
            impact=definition.get('core_impact',p.get('core_impact','具体影响或出现范围尚待明确' if neg else '已被认可的具体体验'))
            tier='优先排查使用问题' if neg and (definition.get('core_impact') or p.get('core_impact')) else '针对场景调查' if neg else '保持已认可体验'
        f['critical_uncertainty']=critical;f['missing_evidence']=missing;f['current_judgment']=f['title'];f['judgment_basis']=f['explanation'];f['action_basis']=basis
        f['priority']={'tier':tier,'potential_impact':impact,'evidence':'原文明示、明确表达的体验或担忧，未独立验证','basis':basis}
        f['recommendation']={'kind':'系统据评论推导的行动建议','consumer_direct_request':False,'phenomenon':f['title'],'cause_hypothesis':critical if neg or pending else None,'action':action,'validation':validation,'missing_evidence':missing,'basis_theme_keys':[g['theme_key'] for g in f['groups']],'review_ids':f['review_ids'],'action_type':'核实安全担忧' if pending else '同口径比较' if key[0]=='comparison' else '针对具体问题调查' if neg else '保留具体体验','why':basis}
        sel=CORE_CONFIG['selection'];threshold=min(den,max(sel['positive_min_reviews'],math.ceil(den*sel['positive_min_fraction']))) if pos and not neg else min(den,max(sel['negative_min_reviews'],math.ceil(den*sel['negative_min_fraction'])))
        f['is_core']=bool(pending or causal_returns or tier=='优先排查使用问题' or n>=threshold)
        f['selection_reason']='安全担忧或原文明示的行为影响' if pending or causal_returns else '明确影响使用或成品' if tier=='优先排查使用问题' else '重复出现的具体体验' if f['is_core'] else '支持较少或影响尚不明确，保留在详细主题'
        findings.append(f)
    order=['优先核实安全担忧','优先排查使用问题','针对场景调查','保持已认可体验']
    keeps=sorted([f for f in findings if f['is_core'] and f['polarity']=='优点'],key=lambda f:(-f['count'],f['id']))
    issues=sorted([f for f in findings if f['is_core'] and f['polarity']=='槽点'],key=lambda f:(order.index(f['priority']['tier']),-f['negative_count'],f['id']))
    success={r['review_id'] for r in run['results'] if r['status']=='completed'};failed=list({r['review_id']:{'review_id':r['review_id'],'error':r.get('error','未生成有效结果')} for r in run['results'] if r['status']=='failed'}.values())
    return {'version':VERSION,'rules_version':CORE_CONFIG['version'],'run_id':run['id'],'product':run.get('product','未提供'),'created_at':run.get('created_at'),'requested_model':run.get('model'),'service_base':run.get('base'),'title':'完整批次报告' if len(success)==raw_total else '当前已分析样本报告（尚非完整批次）','raw_count':raw_total,'success':len(success),'failed':len(failed),'unattempted':max(0,raw_total-len(success)-len(failed)),'findings':findings,'keeps':keeps,'issues':issues,'theme_actions':theme_actions,'detail_only_count':sum(not f['is_core'] for f in findings),'selection_note':CORE_CONFIG['selection']['note'],'negative_review_count':len({rid for f in findings for rid in f['negative_review_ids']}),'consumer_expectations':[g for c in agg['categories'] for g in c['groups'] if g['bucket']=='expectation'],'concerns':[g for c in agg['categories'] for g in c['groups'] if g['bucket'] in ['concern','unknown'] and g['polarity']=='槽点'],'behaviors':agg['behaviors'],'failures':failed,'quality_gate':run.get('quality_gate'),'workflow_phase':run.get('phase'),'priority_method':'优先核实安全担忧及明确相关的退货，再关注影响正常使用或成品的具体问题；结合支持范围，不用正面数量抵消负面，不生成精确重要性分数。','limitations':['仅描述当前非随机导入样本，不能代表所有消费者；未提及不等于满意。','计数按review_id去重，表示评论条数；分母为成功分析数，跨主题或倾向的数量不可直接相加。','同一具体主题的不同评价需结合对象、阶段及比较基准理解；原因未明时保留未知。','引用和字段检查不保证语义正确；建议由系统据评论推导，不冒充消费者直接需求。','满意度、复购率及改进效果尚未验证。']}

def markdown(report,include_evidence=True):
    lines=['# '+report['title'],'',report.get('product','')+' · 批次 '+report['run_id'],'',f'成功 {report["success"]}/{report["raw_count"]} 条；失败 {report["failed"]}；未请求 {report["unattempted"]}。','']
    for key,title in [('keeps','值得保持的地方'),('issues','值得关注的问题')]:
        lines+=['## '+title,'']
        if not report[key]:lines+=['当前证据未形成该类核心发现，详细主题仍保留。','']
        for f in report[key]:
            lines+=['### '+f['title'],'',f'依据：{f["explanation"]} 支持 {f["count"]}/{f["denominator"]} 条独立评论。','','行动建议：'+f['recommendation']['action']]
            if f['critical_uncertainty']:lines+=['','关键限制：'+f['critical_uncertainty']]
            lines+=['']
    lines+=['## 样本范围与说明','',report['selection_note'],report['priority_method'],'']+['- '+s for s in report['limitations']]
    if report.get('performance'):
        m=report['performance'];label='复用处理（非首次模型分析）' if m.get('model_calls')==0 else '本轮处理'
        lines+=['',label+'：新请求 '+str(m.get('model_calls',0))+' 次，复用 '+str(m.get('reused_reviews',0))+' 条；端到端 '+str(m.get('total_wall_seconds','未记录'))+' 秒。']
    if include_evidence:
        lines+=['','<details>','<summary>详细主题、行动依据与全部原文证据</summary>','','尚未验证的原因假设不作为结论；以下保留条件、主题和来源。','']
        for f in report['findings']:
            lines+=['### '+f['title'],('核心发现' if f['is_core'] else '详细主题')+f' · {f["count"]}/{f["denominator"]} 条评论；实际正面 {f["positive_count"]}、负面 {f["negative_count"]}、待核实 {f["pending_count"]}。','行动：'+f['recommendation']['action'],'行动依据：'+f['action_basis']]
            if f['critical_uncertainty']:lines+=['关键限制：'+f['critical_uncertainty']]
            if f['missing_evidence']:lines+=['关键缺失：'+'；'.join(f['missing_evidence'])]
            if f['recommendation']['validation']:lines+=['验证方式：'+f['recommendation']['validation']]
            for s in f['sources']:
                comp=s.get('comparison') or evidence.comparison(s)
                lines += [f'- review_id={s["review_id"]} / aspect_id={s["aspect_id"]} · {s["bucket"]}/{s["polarity"]}：{s["claim"]}',f'  原文：{s["evidence"]}',f'  比较依据：{comp["basis"]}；对象：{comp["reference"]}；情境：{s.get("scenario","未知")}']
            for b in f['behavior_links']:lines+=['- 行为：'+b['status']+'；'+b['association']+'；'+b['claim']+'；原文：'+b['evidence']]
            lines+=['']
        lines+=['### 中立、期待、担忧及其他边界（不计已体验优缺点）','']
        for g in report.get('boundary_groups',[]):
            lines+=[g['summary']+'：'+g['description']]
            for s in g['sources']:lines+=['- review_id='+s['review_id']+' / aspect_id='+s['aspect_id']+'：'+s['evidence']]
        for b in report['behaviors']:lines+=['- '+b['status']+'：'+b['claim']+'；review_id='+b['review_id']+'；原文：'+b['evidence']]
        lines+=['','</details>']
    return '\n'.join(lines)+'\n'
