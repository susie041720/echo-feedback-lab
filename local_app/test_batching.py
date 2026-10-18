"""Isolated development fixtures. No formal reviews, no remote model calls."""
import unittest,threading,time,copy,json
from unittest.mock import patch
import app,batching,workflow,evidence,test_app

class BatchTests(unittest.TestCase):
    setUp=test_app.PipelineTests.setUp
    tearDown=test_app.PipelineTests.tearDown
    aspect=test_app.PipelineTests.aspect
    model_success=test_app.PipelineTests.model_success
    guided_dataset=test_app.PipelineTests.guided_dataset
    run_fixture=test_app.PipelineTests.run_fixture
    fixture=test_app.PipelineTests.fixture
    def batch(self,n=3,**settings):
        d=self.guided_dataset(n)
        with patch.object(app.threading,'Thread'):
            r=app.create_run(d,{'workflow':'daily','key':'TEST ONLY','base':'https://example.invalid','model':'TEST','mode':'responses',**settings})
        return d,r
    def test_bounded_overlap_not_merely_fast_mocks(self):
        d,r=self.batch(5,concurrency=2);lock=threading.Lock();release=threading.Event();two=threading.Event();active=[0,0];calls=[]
        def model(raw,*args,**kwargs):
            with lock:
                active[0]+=1;active[1]=max(active);calls.append(raw['text'])
                if active[0]==2:two.set()
            release.wait(3)
            with lock:active[0]-=1
            return self.model_success(raw)
        with patch.object(app,'call_model',side_effect=model),patch.object(app,'summarize_run',wraps=app.summarize_run) as summary:
            worker=threading.Thread(target=batching.execute,args=(app,r['id'],d,'TEST ONLY'));worker.start();self.assertTrue(two.wait(3));self.assertEqual(len(calls),2);release.set();worker.join(5)
            self.assertFalse(worker.is_alive());self.assertEqual(active[1],2);self.assertEqual(summary.call_count,1)
        final=app.load(app.run_path(r['id']));self.assertEqual(final['metrics']['model_calls'],5);self.assertEqual(final['metrics']['success'],5);self.assertEqual(final['metrics']['aggregation_builds'],1)
    def test_failure_finite_retry_other_comments_finish_usage_counts_attempts(self):
        d,r=self.batch(3,concurrency=2,max_retries=1);bad=d['reviews'][0]['raw']['text']
        def model(raw,*args,**kw):
            if raw['text']==bad:raise app.ModelOutputError('TEST ONLY retry','',{'usage':{'total_tokens':7},'http_status':503})
            return self.model_success(raw)
        with patch.object(app,'call_model',side_effect=model):batching.execute(app,r['id'],d,'TEST ONLY')
        final=app.load(app.run_path(r['id']));self.assertEqual(final['metrics']['success'],2);self.assertEqual(final['metrics']['failed'],1);self.assertEqual(final['metrics']['model_calls'],4);self.assertEqual(app.usage_report(final)['tokens_reported']['total_tokens'],24)
        with patch.object(app.threading,'Thread'):second=app.create_run(d,{'workflow':'daily','key':'TEST ONLY','base':r['base'],'model':r['model'],'mode':r['mode'],'max_retries':0})
        with patch.object(app,'call_model',side_effect=self.model_success) as model:batching.execute(app,second['id'],d,'TEST ONLY');self.assertEqual(model.call_count,1)
    def test_pause_saves_inflight_and_resume_reuses(self):
        d,r=self.batch(4,concurrency=1);entered=threading.Event();release=threading.Event()
        def model(raw,*a,**kw):entered.set();release.wait(3);return self.model_success(raw)
        with patch.object(app,'call_model',side_effect=model):
            worker=threading.Thread(target=batching.execute,args=(app,r['id'],d,'TEST ONLY'));worker.start();self.assertTrue(entered.wait(3));batching.pause(app,r['id']);release.set();worker.join(5)
        final=app.load(app.run_path(r['id']));self.assertEqual(final['status'],'paused');self.assertEqual(len(final['results']),1)
        with patch.object(app.threading,'Thread'):second=app.create_run(d,{'workflow':'daily','key':'TEST ONLY','base':r['base'],'model':r['model'],'mode':r['mode']})
        with patch.object(app,'call_model',side_effect=self.model_success) as model:batching.execute(app,second['id'],d,'TEST ONLY');self.assertEqual(model.call_count,3)
        self.assertEqual(app.load(app.run_path(second['id']))['metrics']['reused_reviews'],1)
    def test_progress_poll_no_aggregation_and_compact_does_not_leak_debug(self):
        d,r=self.batch(1)
        r['results']=[{'review_id':d['reviews'][0]['id'],'status':'completed','analysis':{'aspects':[dict(self.aspect(),id='a')],'uncertainties':[]},'raw_output':'TEST ONLY RAW','api':{'usage':{'total_tokens':12}}}]
        with patch.object(app,'_build_thematic_summary',wraps=app._build_thematic_summary) as build:
            for _ in range(3):v=app.run_view(r)
            self.assertEqual(build.call_count,0);self.assertTrue(v['aggregate']['pending']);self.assertNotIn('prompt',v['run']);self.assertNotIn('raw_output',v['effective'][0]);self.assertNotIn('api',v['run']['results'][0])
        self.assertEqual(app.run_view(r,True)['run']['results'][0]['raw_output'],'TEST ONLY RAW')
    def test_finished_poll_builds_once_edits_invalidate(self):
        d,r,a=self.run_fixture();r['status']='completed'
        with patch.object(app,'_build_thematic_summary',wraps=app._build_thematic_summary) as build:
            for _ in range(3):app.run_view(r)
            self.assertEqual(build.call_count,1)
            r['edits'].append({'aspect_id':a['id'],'changes':{'polarity':'槽点'}});app.run_view(r);self.assertEqual(build.call_count,2)
    def test_config_and_input_changes_invalidate_success_cache(self):
        d,r=self.batch(1)
        with patch.object(app,'call_model',side_effect=self.model_success):batching.execute(app,r['id'],d,'TEST ONLY')
        self.assertEqual(len(workflow.cache(app,d,r['analysis_signature'])),1)
        changed=copy.deepcopy(d);changed['reviews'][0]['sha256']='TEST ONLY CHANGED';self.assertEqual(workflow.cache(app,changed,r['analysis_signature']),{})
        self.assertNotEqual(workflow.fingerprint(app,d,dict(r,model='CHANGED')),r['analysis_signature'])
    def test_comparisons_conservative_unknown_not_purchase_before(self):
        source={'subject':'本产品','experience':'实际经历','evidence':'Not as much noise as I thought it would have.'}
        c=evidence.comparison(source);self.assertEqual(c['basis'],'相对于预期');self.assertEqual(c['expectation_timing'],'未知')
        source['evidence']='Faster than the oven.';self.assertEqual(evidence.comparison(source)['basis'],'旧产品或其他产品')
        source.update(evidence='Easy to clean.');self.assertEqual(evidence.comparison(source)['reference'],'未说明比较对象')
    def test_comparison_reads_same_sentence_not_unrelated_next_sentence(self):
        source={'subject':'本产品','experience':'实际经历','evidence':'is far more energy efficient too','evidence_field':'text'}
        raw={'text':'It takes less time compared to the oven and is far more energy efficient too. Easy to clean.'}
        c=evidence.comparison(source,raw);self.assertEqual(c['basis'],'旧产品或其他产品');self.assertIn(c['context_evidence'],raw['text']);self.assertNotIn('Easy to clean',c['context_evidence'])
        source['evidence']='Easy to clean.';raw['text']='Easy to clean. Compared to the oven it is faster.'
        self.assertEqual(evidence.comparison(source,raw)['basis'],'实际体验的直接判断')
    def test_mixed_one_card_union_counts_and_no_score(self):
        d,r,a=self.run_fixture();b=copy.deepcopy(a);b.update(id='neg',theme_key='clean-ease',major_category='cleaning',polarity='槽点');a.update(theme_key='clean-ease',major_category='cleaning');r['results'][0]['analysis']['aspects']=[a,b,dict(b,id='dup')]
        report=app.thematic_summary(r)['report'];self.assertEqual(report['keeps'],[]);f=report['issues'][0];self.assertEqual((f['count'],f['positive_count'],f['negative_count']),(1,1,1));self.assertTrue(f['has_evaluation_difference']);self.assertNotIn('score',json.dumps(f));self.assertEqual(report['negative_review_count'],1)
    def test_different_sound_phases_not_forced_contradiction(self):
        d,r,a=self.run_fixture();a.update(theme_key='operating-noise',major_category='environment',evidence='Not as much noise as I thought it would have.')
        b=dict(a,id='neg',theme_key='startup-noise',polarity='槽点',evidence='The startup sounds wrong.');r['results'][0]['analysis']['aspects']=[a,b]
        report=app.thematic_summary(r)['report'];f=report['issues'][0];self.assertFalse(f['has_evaluation_difference']);self.assertEqual(len(f['comparison_bases']),1);self.assertEqual(f['count'],1);self.assertEqual(report['keeps'][0]['count'],1);self.assertNotEqual(f['id'],report['keeps'][0]['id'])
    def test_safety_concern_return_cause_not_actual_defect_or_customer_count(self):
        d,r,a=self.run_fixture();rid=r['results'][0]['review_id'];text='I returned because it seems dangerous. Could cause a fire.';d['reviews'][0]['raw']['text']=text;app.save(app.dataset_path(d['id']),d)
        concern=dict(a,major_category='reliability',theme_key='basket-heating-control',experience='担心',polarity='槽点',evidence='it seems dangerous. Could cause a fire.')
        behavior=dict(a,id='return',topic='退货',feedback_kind='行为或意向',theme_key='product-return',polarity='中立',evidence='I returned')
        r['results'][0]['analysis']['aspects']=[concern,behavior];f=app.thematic_summary(r)['report']['issues'][0];self.assertEqual(f['negative_count'],0);self.assertEqual(f['pending_count'],1);self.assertEqual(f['behavior_links'][0]['association'],'原文明示退货原因');self.assertEqual(f['priority']['tier'],'优先核实安全担忧')
        links=evidence.behavior_links([dict(concern,review_id=rid)],[dict(behavior,review_id=rid,kind='退货',status='已退货')],{rid:{'text':'I returned it. Also it seems dangerous.'}});self.assertEqual(links[0]['association'],'同条评论另有行为或意向，未确认因果关联')
    def test_neutral_expectation_hearsay_not_core(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,polarity='中立'),dict(a,id='ex',experience='用户期望'),dict(a,id='heard',experience='转述')]
        report=app.thematic_summary(r)['report'];self.assertEqual(report['findings'],[]);self.assertEqual(report['negative_review_count'],0)
    def test_rate_limit_retries_once_and_reduces_concurrency(self):
        d,r=self.batch(1,concurrency=2,max_retries=1);calls=[]
        def model(raw,*a,**kw):
            calls.append(1)
            if len(calls)==1:raise app.ModelOutputError('TEST ONLY rate limit','',{'http_status':429,'retry_after_seconds':0,'usage':None})
            return self.model_success(raw)
        with patch.object(app,'call_model',side_effect=model):batching.execute(app,r['id'],d,'TEST ONLY')
        final=app.load(app.run_path(r['id']));self.assertEqual(final['metrics']['effective_concurrency'],1);self.assertEqual(final['metrics']['model_calls'],2);self.assertEqual(final['status'],'completed');self.assertEqual(app.usage_report(final)['requests_without_usage'],1)
    def test_auth_error_stops_further_requests_and_reports_unattempted(self):
        d,r=self.batch(4,concurrency=1,max_retries=1)
        with patch.object(app,'call_model',side_effect=app.ModelOutputError('TEST ONLY auth','',{'http_status':401,'usage':None})) as model:batching.execute(app,r['id'],d,'TEST ONLY');self.assertEqual(model.call_count,1)
        final=app.load(app.run_path(r['id']));self.assertEqual(final['metrics']['unattempted'],3);self.assertEqual(final['metrics']['failed'],1);self.assertNotEqual(final['status'],'completed')
    def test_retry_limit_and_concurrency_bounds(self):
        for args in [{'concurrency':5},{'concurrency':0},{'max_retries':3},{'request_timeout_seconds':1}]:
            with self.assertRaises(ValueError):batching.settings(args)

if __name__=='__main__':unittest.main()
