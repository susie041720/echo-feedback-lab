"""Evidence-linked aggregation. Categories and semantic theme vocabulary are product config.
No keyword classifier: use explicit model fields, optional edits or signed contextual migration.
"""
import hashlib, json
from pathlib import Path
CONFIG=json.loads((Path(__file__).parent/'config/air_fryer.json').read_text())
AGGREGATION_CONFIG=json.loads((Path(__file__).parent/'config/core_findings.json').read_text())
VERSION='themes-4.1-explicit-alias'
CATEGORIES={k:(v['name'],[]) for k,v in CONFIG['categories'].items()}
BEHAVIOR_THEMES={'product-return':'退货','return':'退货','return-action':'退货','recommendation-intent':'推荐','product-recommendation':'推荐','repurchase-intent':'复购','purchase-intent':'继续购买'}
BEHAVIOR_THEMES.update({'oven-replacement-intent':'替代烤箱意向','dehydrating-function-intent':'尝试脱水意向','continued-experimentation':'继续尝试意向','kitchen-experimentation-expectation':'厨房尝试意向','future-cooking-use':'未来烹饪用途意向','cooking-use-frequency':'日常使用行为','appliance-preference':'日常使用偏好'})
BEHAVIORS={'退货':'已退货','推荐':'推荐意愿','继续购买':'继续购买意愿','复购':'复购意愿','再次购买':'复购意愿'}

def signature(a):
    return hashlib.sha256(json.dumps({k:a.get(k) for k in ['topic','claim','polarity','subject','experience','evidence','major_category','theme_key','feedback_kind']},sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def category(a):
    # No inference from a noun such as "basket" or from the legacy topic name.
    return a.get('major_category') if a.get('major_category') in CATEGORIES else 'other'

def semantic(a,cat):
    key=a.get('theme_key','');key=AGGREGATION_CONFIG.get('theme_aliases',{}).get(key,key);definition=CONFIG['themes'].get(key)
    if definition and definition['category']==cat:return key,definition['name']
    # Unknown themes retain their concrete topic; no broad category-level paraphrase merging.
    return ('custom:'+key if key else 'specific:'+a['topic']+':'+a['claim']),a['topic']

def aggregate(run,results,annotations=None):
    successful={r['review_id'] for r in results if r['status']=='completed'};den=len(successful)
    bins={k:[] for k in CATEGORIES};behaviors=[];unassigned=[];corrections=[];scenes=[];overall=[];legacy_ids=set()
    rules={key:value for row in results for key,value in row.get('reused_annotations',{}).items()}
    rules.update((annotations or {}).get('aspects',{}))
    original_index={a['id']:a for row in run.get('results',[]) for a in row.get('analysis',{}).get('aspects',[])}
    for r in results:
        if r['status']!='completed':continue
        if not r.get('analysis',{}).get('aspects') and not run.get('prompt_version','').startswith('2.0'):legacy_ids.add(r['review_id'])
        if not r.get('analysis',{}).get('aspects'):unassigned.append({'review_id':r['review_id'],'note':r.get('analysis',{}).get('review_note') or '没有足够具体信息'})
        for original in r.get('analysis',{}).get('aspects',[]):
            a=dict(original);note=None;rule=rules.get(a['id']);legacy=not all(k in original for k in ['major_category','theme_key','feedback_kind'])
            if legacy:legacy_ids.add(r['review_id'])
            base=original_index.get(a['id'],original)
            migrated=bool(rule and rule.get('source_signature')==signature(base))
            if migrated:
                edited={k for k in original if original.get(k)!=base.get(k)}
                changes={k:v for k,v in rule.get('changes',{}).items() if k not in edited}
                if edited & {'polarity','experience','subject'}:changes.pop('_bucket',None)
                a.update(changes);note=rule.get('reason');corrections.append({'review_id':r['review_id'],'aspect_id':a['id'],'reason':note,'changes':changes})
            kind=a.get('feedback_kind','产品反馈');cat=category(a);bucket='actual'
            if a['topic'] in BEHAVIORS or (kind=='行为或意向' and (a.get('theme_key') in BEHAVIOR_THEMES or a['subject']=='其他产品')):bucket='behavior'
            elif kind=='行为或意向' and a['experience']!='实际经历':bucket={'用户期望':'expectation','担心':'concern','转述':'reported'}.get(a['experience'],'unknown')
            elif kind=='行为或意向':bucket='behavior'
            elif a.get('_bucket'):bucket=a['_bucket']
            elif a['subject']!='本产品':bucket='reference' if a['subject']=='其他产品' else 'unknown'
            elif a['polarity']=='信息不足':bucket='unknown'
            elif a['experience']!='实际经历':bucket={'用户期望':'expectation','担心':'concern','转述':'reported'}.get(a['experience'],'unknown')
            if legacy and not migrated and 'major_category' not in original and bucket=='actual':bucket='unknown'
            ref={'review_id':r['review_id'],'aspect_id':a['id'],'original_topic':original['topic'],'original_claim':original['claim'],'claim':a['claim'],'evidence':a['evidence'],'evidence_field':a['evidence_field'],'subject':a['subject'],'experience':a['experience'],'polarity':a['polarity'],'context_note':note,'feedback_kind':kind,'confidence':a.get('confidence','未提供'),'bucket':bucket,'scenario':a.get('scenario','未说明')}
            if kind=='使用背景':scenes.append(ref);continue
            if kind=='整体评价':overall.append(ref);continue
            if bucket=='behavior':
                action=BEHAVIOR_THEMES.get(a.get('theme_key'),a['topic']);status='已发生的退货行为' if action=='退货' and a['experience']=='实际经历' else '表达的行为或意愿（是否已实施不据此推断）'
                behaviors.append(dict(ref,kind=BEHAVIORS.get(action,action),status=status));continue
            if a.get('scenario') and a['scenario']!='未说明':scenes.append(dict(ref,scenario=a['scenario']))
            key,title=semantic(a,cat)
            bins[cat].append({'key':key,'title':title,'bucket':bucket,'polarity':a['polarity'],'ref':ref})
    categories=[]
    for cat,entries in bins.items():
        if not entries:continue
        merged={}
        for e in entries:
            key=(e['bucket'],e['polarity'],e['key'])
            if key not in merged:merged[key]={'theme_key':e['key'],'summary':e['title'],'bucket':e['bucket'],'polarity':e['polarity'],'sources':[]}
            # Same extraction may be encountered twice, but never create duplicate evidence entries.
            if not any(s['review_id']==e['ref']['review_id'] and s['aspect_id']==e['ref']['aspect_id'] for s in merged[key]['sources']):merged[key]['sources'].append(e['ref'])
        groups=list(merged.values())
        for g in groups:
            g['review_ids']=sorted({s['review_id'] for s in g['sources']});g['count']=len(g['review_ids']);g['percent']=round(g['count']/den*100,1) if den else None
            g['subissues']=list(dict.fromkeys(s['claim'] for s in g['sources']))
            g['support_label']='有一条评论提到' if g['count']==1 else f'{g["count"]} 条评论提到'
            definition=CONFIG['themes'].get(g['theme_key'],{})
            semantic_key=g['theme_key'][7:] if g['theme_key'].startswith('custom:') else g['theme_key']
            descriptions=AGGREGATION_CONFIG.get('theme_descriptions',{}).get(semantic_key,definition.get('descriptions',{}))
            g['description']=descriptions.get(g['polarity'],g['subissues'][0]) if g['bucket']=='actual' else g['subissues'][0]
            conditions=list(dict.fromkeys(s['scenario'] for s in g['sources'] if s.get('scenario') and s['scenario']!='未说明'))
            if conditions:g['description']=g['description'].rstrip('。')+'。涉及情境：'+'；'.join(c.rstrip('。') for c in conditions)+'。'
        ids={e['ref']['review_id'] for e in entries};actual=[g for g in groups if g['bucket']=='actual'];pos=[g for g in actual if g['polarity']=='优点'];neg=[g for g in actual if g['polarity']=='槽点'];neutral=[g for g in actual if g['polarity']=='中立']
        def counts(gs):return len({rid for g in gs for rid in g['review_ids']})
        conflicts=sorted({g['theme_key'].removeprefix('custom:') for g in pos}&{g['theme_key'].removeprefix('custom:') for g in neg}&set(AGGREGATION_CONFIG.get('comparable_specific_themes',[])))
        parts=[]
        for gs,verb in [(pos,'认可'),(neg,'指出'),(neutral,'描述')]:
            if gs:parts.append(f'{"有一条评论" if gs[0]["count"]==1 else str(gs[0]["count"])+" 条评论"}{verb}“{gs[0]["summary"]}”')
        judgment='；'.join(parts)+'。' if parts else '当前仅有待核实或非亲历信息，不计入实际优缺点。'
        if conflicts:judgment+='同一具体主题存在不同评价，比较基准或条件可不同，不据此认定事实矛盾。'
        categories.append({'key':cat,'name':CATEGORIES[cat][0],'review_ids':sorted(ids),'count':len(ids),'actual_count':counts(actual),'positive_count':counts(pos),'negative_count':counts(neg),'neutral_count':counts(neutral),'conflict_theme_keys':conflicts,'judgment':judgment,'groups':groups})
    compatibility={'legacy_review_count':len(legacy_ids),'original_prompt_version':run.get('prompt_version','未记录'),'new_rules_model_reanalysis':not bool(legacy_ids),'neutral_coverage':'旧版未系统提取中立用途与背景，当前缺项不能解释为没有相关描述；如需完整覆盖，建议仅重跑已分析的8条。' if legacy_ids else '按新版字段归纳；仍需抽检语义准确性。','migration_method':'对已存在片段逐项核对并单独保存迁移，未生成新的模型输出。' if legacy_ids else '使用保存的分类与评价字段。'}
    return {'version':VERSION,'taxonomy_id':CONFIG['id'],'taxonomy_version':CONFIG['version'],'taxonomy_categories':CONFIG['categories'],'feedback_kinds':CONFIG['feedback_kinds'],'method':'explicit_semantic_fields_with_signed_legacy_migration','method_label':'旧版模型提取＋有留痕的迁移（未重跑）' if legacy_ids else '按新版规则真实模型提取；主题归纳与数量由程序计算','compatibility':compatibility,'run_id':run['id'],'source_edit_count':len(run.get('edits',[])),'analyzed_count':den,'categories':categories,'behaviors':behaviors,'behavior_review_count':len({b['review_id'] for b in behaviors}),'scenarios':scenes,'overall_evaluations':overall,'unassigned_reviews':unassigned,'context_corrections':corrections,'new_model_requests':0,'provisional':True,'counting_note':'分母为成功分析的独立评论数。每个类别、主题及倾向分别按 review_id 去重；跨类别或跨倾向可以涉及同一评论，占比不可相加。中立、期待、担忧及待确认不计入优点或槽点。'}
