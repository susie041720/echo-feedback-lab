"""Small, bounded background batch runner. Keys stay in worker memory only."""
import copy,time,threading,statistics,concurrent.futures
VERSION='bounded-batch-1'
CANCEL_EVENTS={}

def settings(config):
    def number(name,default,low,high):
        try:value=int(config.get(name,default))
        except (ValueError,TypeError):raise ValueError('批量配置无效：'+name)
        if not low<=value<=high:raise ValueError('批量配置超出范围：'+name)
        return value
    return {'concurrency':number('concurrency',2,1,4),'max_retries':number('max_retries',1,0,2),'request_timeout_seconds':number('request_timeout_seconds',120,30,180)}

def pause(app,rid):
    event=CANCEL_EVENTS.get(rid)
    if not event:raise ValueError('当前批次未运行，已有结果已保存')
    event.set()
    with app.LOCK:
        run=app.load(app.run_path(rid));run['phase']='pausing';app.save(app.run_path(rid),run)
    return {'status':'pausing','note':'停止提交新请求，在途请求结束后保存；恢复时复用同版本成功结果。'}

def execute(app,rid,d,key,force_fresh=False,summarize=True):
    import workflow
    started=time.monotonic();run=app.load(app.run_path(rid));config=settings(run.get('execution',{}));rows={row['id']:row for row in d['reviews']};cached={} if force_fresh else workflow.cache(app,d,run['analysis_signature']);cancel=threading.Event();CANCEL_EVENTS[rid]=cancel
    rate_lock=threading.Lock();cooldown=[0.0];effective_concurrency=[config['concurrency']]
    def mutate(fn):
        with app.LOCK:
            current=app.load(app.run_path(rid));fn(current);app.save(app.run_path(rid),current)
    metrics={'execution_version':VERSION,'concurrency':config['concurrency'],'effective_concurrency':config['concurrency'],'max_retries':config['max_retries'],'started_at':app.now(),'model_calls':0,'reused_reviews':0,'aggregation_builds':0,'aggregation_seconds':0.0,'request_seconds_sum':0.0}
    mutate(lambda r:r.update(metrics=metrics,request_log=[],phase='full_batch'))
    ids=run['target_review_ids'];saved_ids={r['review_id'] for r in run['results']};todo=[]
    for review_id in ids:
        if review_id in saved_ids:continue
        if review_id in cached:
            item=copy.deepcopy(cached[review_id]);mutate(lambda r,item=item:(r['results'].append(item),r['metrics'].__setitem__('reused_reviews',r['metrics']['reused_reviews']+1)))
        else:todo.append(review_id)
    def one(review_id):
        attempts=[];feedback=None
        for attempt_no in range(1,config['max_retries']+2):
            if cancel.is_set() and not attempts:return None
            with rate_lock:delay=max(0,cooldown[0]-time.monotonic())
            if delay and cancel.wait(delay):
                if not attempts:return None
                result=copy.deepcopy(attempts[-1]);result['attempts']=attempts;return result
            attempt_id=app.uid();request_start=time.monotonic();entry={'id':attempt_id,'review_id':review_id,'attempt':attempt_no,'started_at':app.now(),'status':'in_flight'}
            mutate(lambda r:(r['request_log'].append(entry),r['metrics'].__setitem__('model_calls',r['metrics']['model_calls']+1)))
            result={'review_id':review_id,'status':'failed','raw_sha256':rows[review_id]['sha256'],'request_reused':False}
            try:
                kwargs={'request_timeout_seconds':config['request_timeout_seconds']}
                if feedback:kwargs['repair_feedback']=feedback
                analysis,api=app.call_model(rows[review_id]['raw'],d['product'],key,run['base'],run['model'],run['mode'],**kwargs)
                for aspect in analysis['aspects']:aspect['id']=app.uid()
                result.update(status='completed',analysis=analysis,raw_output=api.pop('raw_output',None),api=api)
            except Exception as error:
                msg=str(error) if isinstance(error,ValueError) else '模型请求未取得有效响应'
                result.update(error=msg.replace(key,'[REDACTED]')[:350] if key else msg[:350],exception_type=type(error).__name__)
                if isinstance(error,app.ModelOutputError):result.update(raw_output=error.raw_output,api=error.api)
            elapsed=round(time.monotonic()-request_start,4);result.update(elapsed_seconds=elapsed,attempt=attempt_no,attempt_id=attempt_id)
            attempts.append(copy.deepcopy(result))
            def finished(r):
                log=next(x for x in r['request_log'] if x['id']==attempt_id);log.update(status=result['status'],finished_at=app.now(),elapsed_seconds=elapsed,http_status=result.get('api',{}).get('http_status'),exception_type=result.get('exception_type'))
                r['metrics']['request_seconds_sum']+=elapsed
            mutate(finished)
            if result['status']=='completed':break
            http=result.get('api',{}).get('http_status')
            if http in [400,401,403,404,422]:
                cancel.set();mutate(lambda r:r.update(stop_reason='接口配置或认证错误，停止发送后续请求；未请求项保留为未完成。'));break
            if http==429:
                with rate_lock:effective_concurrency[0]=1;cooldown[0]=time.monotonic()+min(5,max(1,result.get('api',{}).get('retry_after_seconds',1)))
                mutate(lambda r:r['metrics'].__setitem__('effective_concurrency',1))
            if attempt_no>config['max_retries'] or cancel.is_set():break
            feedback=('前次字段或逐字引文校验未通过。请重新完整读取原文，保持上下文和不确定性，不为通过校验添加事实。校验原因：'+result.get('error','')) if result.get('raw_output') else None
            if cancel.wait(min(2**(attempt_no-1),4)):break
        result['attempts']=attempts
        return result
    try:
        iterator=iter(todo);in_flight={}
        with concurrent.futures.ThreadPoolExecutor(max_workers=config['concurrency'],thread_name_prefix='feedback') as pool:
            exhausted=False
            while in_flight or (not exhausted and not cancel.is_set()):
                while not exhausted and not cancel.is_set() and len(in_flight)<effective_concurrency[0]:
                    try:review_id=next(iterator)
                    except StopIteration:exhausted=True;break
                    in_flight[pool.submit(one,review_id)]=review_id
                if not in_flight:break
                done,_=concurrent.futures.wait(in_flight,return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    review_id=in_flight.pop(future);result=future.result()
                    if result is not None:mutate(lambda r,result=result:r['results'].append(result))
        final=app.load(app.run_path(rid));complete=len({r['review_id'] for r in final['results'] if r['status']=='completed'})==len(ids)
        status='completed' if complete else 'paused' if cancel.is_set() and not final.get('stop_reason') else 'partial_or_failed'
        mutate(lambda r:r.update(status=status,phase='complete' if complete else 'paused' if status=='paused' else 'full_batch_partial',finished_at=app.now()))
    except Exception as error:
        mutate(lambda r:r.update(status='partial_or_failed',phase='full_batch_partial',finished_at=app.now(),coordinator_error=type(error).__name__))
    finally:
        final=app.load(app.run_path(rid));latencies=[x['elapsed_seconds'] for x in final.get('request_log',[]) if 'elapsed_seconds' in x]
        def close_metrics(r):
            successful={x['review_id'] for x in r['results'] if x['status']=='completed'};failed={x['review_id'] for x in r['results'] if x['status']=='failed'}
            r['metrics'].update(extraction_wall_seconds=round(time.monotonic()-started,4),success=len(successful),failed=len(failed),unattempted=len(ids)-len(successful)-len(failed),request_latency_median_seconds=round(statistics.median(latencies),4) if latencies else None,request_latency_max_seconds=max(latencies) if latencies else None)
        mutate(close_metrics)
        if summarize and any(x['status']=='completed' for x in final['results']):
            summary_start=time.monotonic();app.summarize_run(rid);duration=round(time.monotonic()-summary_start,4)
            mutate(lambda r:r['metrics'].update(aggregation_builds=1,aggregation_seconds=duration))
        mutate(lambda r:r['metrics'].update(total_wall_seconds=round(time.monotonic()-started,4),finished_at=app.now()))
        if summarize:
            snapshot=app.SUMMARIES/(rid+'.json')
            if snapshot.exists():
                value=app.load(snapshot);value['aggregate']['report']['performance']=app.load(app.run_path(rid))['metrics'];value['aggregate']['report']['brief_markdown']=app.insights.markdown(value['aggregate']['report'],include_evidence=False);app.save(snapshot,value)
        CANCEL_EVENTS.pop(rid,None)
