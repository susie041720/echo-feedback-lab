"""Derived per-product snapshots; source batches and model outputs are never changed."""
import copy,hashlib,json
VERSION='cumulative-1'
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def product_key(d):
    asins={r['raw'].get('asin','').strip() for r in d['reviews']};asins.discard('')
    if len(asins)==1 and all(r['raw'].get('asin') for r in d['reviews']):return 'asin:'+next(iter(asins))
    return 'label:'+d['product'].strip().casefold()
def identity(d,row):
    raw=row['raw'];source=raw.get('source','').strip().casefold();rid=raw.get('review_id','').strip()
    if rid:return digest([product_key(d),source,'review_id',rid]),'source_review_id'
    if raw.get('source_record_sha256'):return digest([product_key(d),source,'source_record_sha256',raw['source_record_sha256']]),'source_record_sha256'
    return digest([product_key(d),'exact_record',raw]),'exact_record_fallback'
def compatible(run,target):return tuple(run.get(k) for k in ['prompt_version','model','mode'])==target

def refresh(app):
    datasets=[app.load(p) for p in app.DATA.glob('dataset_*.json')];datasets=[d for d in datasets if not d.get('derived_kind')]
    runs=[app.load(p) for p in app.RUNS.glob('*.json')];runs=[r for r in runs if not r.get('derived_kind')]
    groups={}
    for d in datasets:groups.setdefault(product_key(d),[]).append(d)
    for key,batches in groups.items():
        if len(batches)<2:continue
        batches.sort(key=lambda d:(d['created_at'],d['id']))
        ids={d['id'] for d in batches};history=sorted([r for r in runs if r.get('dataset_id') in ids],key=lambda r:(r['created_at'],r['id']),reverse=True)
        if any(r['status']=='running' for r in history):continue # Do not snapshot an in-flight mutable run.
        if not history:continue
        target=tuple(history[0].get(k) for k in ['prompt_version','model','mode'])
        stamp=[(p.name,p.stat().st_mtime_ns) for p in (app.ROOT/'curation').glob('*.json')]
        signature=digest([VERSION,batches,history,stamp,app.thematic.VERSION,app.insights.VERSION,app.evidence.VERSION])
        did=digest(['cumulative_dataset',key])[:32];rid=digest(['cumulative_run',did,signature])[:32]
        if app.run_path(rid).exists() and app.dataset_path(did).exists():continue
        latest={};effective={}
        for run in history:
            for result in run['results']:
                pair=(run['dataset_id'],result['review_id'])
                if pair not in latest:latest[pair]=(run,result)
        records={};duplicate=[];fallback=0
        for d in batches:
            for row in d['reviews']:
                stable,method=identity(d,row);stable=stable[:32]
                origin={'batch_id':d['id'],'batch_label':d.get('filename') or d['product'],'batch_product':d['product'],'review_id':row['id']}
                chosen=latest.get((d['id'],row['id']));candidate=None
                if chosen:
                    run,result=chosen;origin['run_id']=run['id'];candidate=copy.deepcopy(result)
                    if not compatible(run,target):candidate.update(status='failed',error='提取版本、模型或接口模式不兼容；需在原批次定向处理',analysis={})
                    elif candidate['status']=='completed':
                        if run['id'] not in effective:effective[run['id']]={r['review_id']:r for r in app.aggregation_effective(run)}
                        candidate=copy.deepcopy(effective[run['id']][row['id']])
                    candidate.update(source_run_id=run['id'],request_reused=True)
                if not candidate:candidate={'status':'unanalyzed','analysis':{},'error':'尚无当前兼容版本的有效提取结果','request_reused':True}
                candidate['review_id']=stable
                if stable not in records:records[stable]={'row':dict(copy.deepcopy(row),id=stable,origins=[]),'result':candidate,'method':method}
                else:
                    duplicate.append({'stable_review_id':stable,'duplicate_origin':origin})
                    # Prefer a valid current snapshot across duplicate imports, never add counts.
                    if records[stable]['result']['status']!='completed' and candidate['status']=='completed':records[stable].update(result=candidate,row=dict(copy.deepcopy(row),id=stable,origins=records[stable]['row']['origins']))
                records[stable]['row']['origins'].append(origin)
                fallback+=method=='exact_record_fallback'
        reviews=[v['row'] for v in records.values()];results=[v['result'] for v in records.values()];success=sum(r['status']=='completed' for r in results)
        metadata={'source_batch_ids':sorted(ids),'source_batches':[{'id':d['id'],'label':d.get('filename') or d['product'],'product':d['product'],'raw_count':len(d['reviews'])} for d in batches],'source_record_count':sum(len(d['reviews']) for d in batches),'duplicate_count':len(duplicate),'exact_record_fallback_count':fallback,'input_signature':signature,'identity_note':'优先产品+来源+原始review_id，其次源行SHA256；缺失时仅按完整原始记录精确去重，不按正文相似度合并。'}
        d={'id':did,'product':batches[0]['product'],'filename':'全部批次／累计分析','created_at':app.now(),'derived_kind':'product_cumulative','reviews':reviews,'duplicates':duplicate,'skipped_empty_rows':[],'columns':sorted({k for r in reviews for k in r['raw']}),'provenance':{'usage_scope':'local_research_only' if any(x.get('provenance',{}).get('usage_scope')=='local_research_only' for x in batches) else 'user_uploaded'},'cumulative':metadata}
        run={'id':rid,'dataset_id':did,'product':d['product'],'created_at':app.now(),'finished_at':app.now(),'status':'completed' if success==len(results) else 'partial_or_failed','derived_kind':'product_cumulative','workflow':'cumulative_v1','model':history[0].get('model'),'mode':history[0].get('mode'),'prompt_version':history[0].get('prompt_version'),'review_ids':[r['id'] for r in reviews],'results':results,'edits':[],'human_reviews':[],'new_model_requests':0,'cumulative':metadata,'metrics':{'model_calls':0,'reused_reviews':success,'success':success,'failed':sum(r['status']=='failed' for r in results),'automatic_retries':0,'purpose':'同产品跨批次去重后重新归纳，未调用模型'}}
        app.save(app.dataset_path(did),d);app.save(app.run_path(rid),run)
