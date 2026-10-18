"""Opt-in development measurement. Real outputs isolated from ordinary analysis/cache."""
import threading,copy,types,time
import batching,workflow

def folder(app):return app.ROOT/'benchmarks'
def view(app,i):
    value=app.load(folder(app)/(app.valid_id(i)+'.json'))
    children=[]
    for child in value.get('children',[]):
        path=folder(app)/(child['id']+'.json')
        if path.exists():
            r=app.load(path);children.append(dict(child,status=r['status'],metrics=r.get('metrics',{}),usage=app.usage_report(r)))
    value['children']=children;return value

def create(app,d,config):
    key=config.get('key','').strip() or app.os.environ.get('OPENAI_API_KEY','')
    if not key:raise ValueError('测速需要本地输入模型密钥；不会保存。')
    parsed=app.urlparse(config.get('base',''))
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or not config.get('model') or config.get('mode') not in ['responses','chat']:raise ValueError('模型配置无效')
    # Use the same full comments in both arms, in the same order. No generated/shortened text.
    indexes=[0,13,31,32] if len(d['reviews'])>=33 else list(range(min(4,len(d['reviews']))))
    chosen=[d['reviews'][i]['id'] for i in indexes];i=app.uid()
    parent={'id':i,'dataset_id':d['id'],'created_at':app.now(),'status':'running','purpose':'development_real_serial_vs_concurrent','review_ids':chosen,'children':[],'note':'同一组完整真实评论，各新调用一次；顺序串行1→并发2，零自动重试。小样本、时段波动和输出长度可能影响耗时，不能外推大规模效果。'}
    folder(app).mkdir(exist_ok=True);app.save(folder(app)/(i+'.json'),parent)
    config={k:config[k] for k in ['base','model','mode']}
    def execute():
        adapter=types.SimpleNamespace(**vars(app));adapter.run_path=lambda rid:folder(app)/(app.valid_id(rid)+'.json')
        try:
            for concurrency in [1,2]:
                rid=app.uid();run={'id':rid,'dataset_id':d['id'],'product':d['product'],'created_at':app.now(),'status':'running','phase':'full_batch','workflow':'daily_batch_v1','analysis_signature':workflow.fingerprint(app,d,config),'prompt_version':app.PROMPT_VERSION,'prompt':app.PROMPT,'schema':app.SCHEMA,'review_ids':chosen,'target_review_ids':chosen,'trial_review_ids':[],'results':[],'edits':[],'human_reviews':[],'auxiliary_requests':[],'execution':{'concurrency':concurrency,'max_retries':0,'request_timeout_seconds':120},**config}
                app.save(adapter.run_path(rid),run)
                parent['children'].append({'id':rid,'concurrency':concurrency});app.save(folder(app)/(i+'.json'),parent)
                batching.execute(adapter,rid,d,key,force_fresh=True,summarize=False)
                final=app.load(adapter.run_path(rid))
                if final.get('stop_reason'):parent['error']=final['stop_reason'];break
            parent.update(status='finished',finished_at=app.now());app.save(folder(app)/(i+'.json'),parent)
        except Exception as e:
            parent.update(status='failed',error=type(e).__name__,finished_at=app.now());app.save(folder(app)/(i+'.json'),parent)
    threading.Thread(target=execute,daemon=True).start()
    return parent

def latest(app):
    parents=[]
    for path in folder(app).glob('*.json'):
        value=app.load(path)
        if value.get('purpose')=='development_real_serial_vs_concurrent':parents.append(value)
    return view(app,max(parents,key=lambda x:x['created_at'])['id']) if parents else None

def historical_timings(app,dataset_id):
    """Recover recorded stage walls only. Never infer missing timing from file mtimes."""
    import datetime
    rows=[]
    for path in app.RUNS.glob('*.json'):
        r=app.load(path)
        if r.get('dataset_id')!=dataset_id or r.get('prompt_version')!=app.PROMPT_VERSION:continue
        new=[x for x in r['results'] if not x.get('request_reused')]
        if not new or not r.get('finished_at'):continue
        try:wall=(datetime.datetime.fromisoformat(r['finished_at'])-datetime.datetime.fromisoformat(r['created_at'])).total_seconds()
        except (ValueError,TypeError):continue
        reused=sum(bool(x.get('request_reused')) for x in r['results']);aux=r.get('auxiliary_requests',[])
        # This historical stage stopped after initial extraction, before any semantic audit/repair.
        first_only=not reused and not aux and r.get('phase')=='trial_failed'
        if not first_only:continue
        rows.append({'run_id':r['id'],'created_at':r['created_at'],'finished_at':r['finished_at'],'kind':'historical_first_v2_extraction_no_result_reuse','label':'首次按当前提取规则处理原8条（历史实录）','review_count':len(r['review_ids']),'concurrency':1,'concurrency_basis':'保留的guided提取实现为串行；历史记录无单独并发字段','new_model_requests':len(new),'reused_reviews':0,'automatic_retries':0,'auxiliary_requests':0,'extraction_stage_wall_seconds':round(wall,4),'extraction_timing_scope':'由批次创建到提取阶段结束，包含启动和本地校验开销；非纯服务端推理耗时','aggregation_seconds':None,'end_to_end_including_aggregation_seconds':None,'success':sum(x['status']=='completed' for x in r['results']),'failed':sum(x['status']=='failed' for x in r['results']),'limits':'历史记录未保存汇总开始/结束时刻，汇总与含汇总端到端耗时无法恢复；这不是50条全新分析测速。'})
    return sorted(rows,key=lambda x:x['created_at'])[:1]
