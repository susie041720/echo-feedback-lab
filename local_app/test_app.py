"""Contract tests only. Synthetic TEST ONLY fixtures are never loaded into the UI.
These tests do NOT demonstrate an actual remote model call or analysis quality.
"""
import unittest, tempfile, json, io, zipfile
from pathlib import Path
from unittest.mock import patch
import app

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.p=Path(self.temp.name)
        self.data_patch=patch.object(app,'DATA',self.p/'data');self.run_patch=patch.object(app,'RUNS',self.p/'runs');self.summary_patch=patch.object(app,'SUMMARIES',self.p/'summaries');self.summary_patch.start();self.data_patch.start();self.run_patch.start();app.DATA.mkdir();app.RUNS.mkdir();(app.DATA/'source_report.md').write_text('TEST ONLY')
    def tearDown(self):self.data_patch.stop();self.run_patch.stop();self.summary_patch.stop();self.temp.cleanup()
    def fixture(self):return app.import_csv('text,title,rating,source,custom\nTEST ONLY alpha,Test,5,contract,untouched\nTEST ONLY beta,Test,,contract,unknown\n','TEST ONLY PRODUCT')
    def aspect(self,quote='TEST ONLY alpha',polarity='优点',subject='本产品',experience='实际经历'):
        return {'major_category':'other','theme_key':'test-topic','feedback_kind':'产品反馈','topic':'TEST ONLY topic','polarity':polarity,'claim':'TEST ONLY contract assertion','evidence':quote,'evidence_field':'text','subject':subject,'experience':experience,'scenario':'未说明','confidence':'低','recommendation_kind':'无需建议','recommendation':'','rationale':''}
    def run_fixture(self):
        d=self.fixture();i=app.uid();a=self.aspect();a['id']=app.uid();b=dict(a,id=app.uid());c=dict(a,id=app.uid(),subject='其他产品',polarity='槽点');r={'id':i,'dataset_id':d['id'],'review_ids':[x['id'] for x in d['reviews']],'results':[{'review_id':d['reviews'][0]['id'],'status':'completed','analysis':{'uncertainties':[],'aspects':[a,b,c],'review_note':''}},{'review_id':d['reviews'][1]['id'],'status':'failed','error':'TEST ONLY'}],'edits':[]};app.save(app.run_path(i),r);return d,r,a
    def test_preserve_fields_unknown_and_original_upload(self):
        d=self.fixture();self.assertEqual(d['reviews'][0]['raw']['custom'],'untouched');self.assertEqual(d['reviews'][1]['raw']['rating'],'');self.assertNotIn('topic',d['reviews'][0]['raw']);self.assertTrue((app.DATA/('upload_'+d['id']+'.csv')).exists())
    def test_exact_dedup_and_blank_audit(self):
        d=app.import_csv('text,author\nTEST ONLY,a\nTEST ONLY,a\nTEST ONLY,b\n ,c\n','TEST');self.assertEqual(len(d['reviews']),2);self.assertEqual(len(d['duplicates']),1);self.assertEqual(len(d['skipped_empty_rows']),1)
    def test_missing_text_empty_and_malformed(self):
        for text in ['body\nx\n','text\n \n','text,title\na,b,c\n','text,text\na,b\n']:
            with self.assertRaises(ValueError):app.import_csv(text,'TEST')
    def test_multiline_csv(self):
        d=app.import_csv('text,title\n"TEST ONLY line1\nline2",T\n','TEST');self.assertIn('\n',d['reviews'][0]['raw']['text'])
    def test_evidence_must_match_exact_field(self):
        result={'uncertainties':[],'review_note':'','aspects':[self.aspect()]};self.assertEqual(app.check_analysis(result,{'text':'TEST ONLY alpha'}),result)
        with self.assertRaises(ValueError):app.check_analysis(result,{'text':'TEST ONLY ALPHA'})
    def test_missing_or_extra_fields_rejected(self):
        a=self.aspect();a['invented']='bad'
        with self.assertRaises(ValueError):app.check_analysis({'uncertainties':[],'review_note':'','aspects':[a]},{'text':'TEST ONLY alpha'})
    def test_uncertain_empty_aspects_accepted(self):self.assertEqual(app.check_analysis({'uncertainties':[],'review_note':'信息不足','aspects':[]},{} )['aspects'],[])
    def test_direct_demand_requires_rationale(self):
        a=self.aspect();a['recommendation_kind']='消费者直接需求';a['recommendation']='TEST'
        with self.assertRaises(ValueError):app.check_analysis({'uncertainties':[],'review_note':'','aspects':[a]},{'text':'TEST ONLY alpha'})
    def test_unique_review_denominator_and_other_exclusion(self):
        d,r,a=self.run_fixture();s=app.statistics(r);self.assertEqual(s['completed_reviews'],1);self.assertEqual(s['themes'][0]['count'],1);self.assertEqual(s['themes'][0]['percent'],100);self.assertEqual(s['excluded_aspects'],1)
    def test_concern_excluded(self):
        d,r,a=self.run_fixture()
        for x in r['results'][0]['analysis']['aspects']:x['experience']='担心或预期'
        self.assertEqual(app.statistics(r)['themes'],[])
    def test_edit_overlay_keeps_original_and_recomputes(self):
        d,r,a=self.run_fixture();updated=app.edit_run(r['id'],a['id'],{'topic':'human topic','polarity':'槽点'});self.assertEqual(updated['results'][0]['analysis']['aspects'][0]['topic'],'TEST ONLY topic');self.assertEqual(app.effective(updated)[0]['analysis']['aspects'][0]['topic'],'human topic');self.assertEqual(len(app.statistics(updated)['themes']),2)
        with self.assertRaises(ValueError):app.edit_run(r['id'],a['id'],{'evidence':'invented'})
    def test_export_raw_and_analysis_separate(self):
        d,r,a=self.run_fixture();z=zipfile.ZipFile(io.BytesIO(app.export_zip(d,r)));self.assertIn('raw_upload.csv',z.namelist());self.assertIn('statistics.json',z.namelist());self.assertEqual(json.loads(z.read('raw_reviews.json'))['id'],d['id']);self.assertNotIn('statistics.json',zipfile.ZipFile(io.BytesIO(app.export_zip(d))).namelist())
    def test_no_api_key_means_no_run(self):
        d=self.fixture()
        with patch.dict(app.os.environ,{'OPENAI_API_KEY':''}):
            with self.assertRaises(ValueError):app.create_run(d,{'model':'test'})
        self.assertEqual(list(app.RUNS.glob('*.json')),[])
    def test_invalid_ids(self):
        for i in ['../secret','x'*32,'']:
            with self.assertRaises(ValueError):app.run_path(i)
    def test_worker_partial_failure_not_in_denominator(self):
        d=self.fixture();i=app.uid();r={'id':i,'review_ids':[x['id'] for x in d['reviews']],'results':[],'edits':[]};app.save(app.run_path(i),r)
        with patch.object(app,'call_model',side_effect=[({'uncertainties':[],'review_note':'TEST ONLY','aspects':[self.aspect()]},{}),ValueError('TEST ONLY failure')]):app.worker(i,d,'secret-test-key','https://example.invalid','test','responses')
        r=app.load(app.run_path(i));self.assertEqual(r['status'],'partial_or_failed');self.assertEqual(app.statistics(r)['completed_reviews'],1);self.assertTrue((app.SUMMARIES/(i+'.json')).exists())


    def test_trial_selection_does_not_send_all_fifty(self):
        d=app.import_csv('text\n'+'\n'.join('TEST ONLY '+str(i) for i in range(50)),'TEST')
        ids=[d['reviews'][i]['id'] for i in range(8)]
        with patch.object(app.threading,'Thread') as thread:
            r=app.create_run(d,{'key':'TEST ONLY KEY','model':'test','review_ids':ids})
        self.assertEqual(len(r['review_ids']),8)
        self.assertEqual(len(thread.call_args.kwargs['args'][1]['reviews']),8)
        self.assertEqual(len(app.load(app.dataset_path(d['id']))['reviews']),50)
        self.assertNotIn('TEST ONLY KEY',app.run_path(r['id']).read_text())
    def test_uncertainty_quote_must_be_grounded(self):
        result={'uncertainties':[{'question':'TEST','reason':'TEST','evidence':'invented','evidence_field':'text'}],'review_note':'','aspects':[]}
        with self.assertRaises(ValueError):app.check_analysis(result,{'text':'TEST ONLY'})
    def test_failed_output_preserves_usage_and_raw_response(self):
        d=self.fixture();i=app.uid();r={'id':i,'review_ids':[x['id'] for x in d['reviews']],'results':[],'edits':[],'model':'requested-test'};app.save(app.run_path(i),r)
        error=app.ModelOutputError('TEST ONLY validation error','TEST ONLY invalid output',{'reported_model':'actual-test','usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}})
        with patch.object(app,'call_model',side_effect=error):app.worker(i,d,'TEST ONLY KEY','https://example.invalid','test','chat')
        r=app.load(app.run_path(i));self.assertEqual(r['results'][0]['raw_output'],'TEST ONLY invalid output');u=app.usage_report(r);self.assertEqual(u['tokens_reported']['total_tokens'],28);self.assertEqual(u['reported_models'],['actual-test'])
    def test_no_returned_usage_is_unknown_not_zero(self):
        self.assertIsNone(app.usage_report({'model':'test','results':[{'status':'failed'}]})['tokens_reported'])
    def test_incremental_summary_keeps_evidence_references(self):
        d,r,a=self.run_fixture();r['status']='running';app.save(app.run_path(r['id']),r)
        self.assertGreater(app.summarize_run(r['id'])['statistics']['completed_reviews'],0)
        self.assertEqual(app.load(app.run_path(r['id']))['status'],'running')
        r['status']='completed';app.save(app.run_path(r['id']),r)
        with patch.object(app,'SUMMARIES',self.p/'summaries'):
            result=app.summarize_run(r['id'])
        self.assertEqual(result['theme_evidence'][0]['extractions'][0]['aspect_id'],a['id'])
    def test_human_review_does_not_overwrite_output(self):
        d,r,a=self.run_fixture();before=r['results'];updated=app.record_review(r['id'],r['review_ids'][0],'需要修正','TEST ONLY note');self.assertEqual(before,updated['results']);self.assertEqual(updated['human_reviews'][0]['status'],'需要修正')


    def test_connection_check_does_not_send_review_payload(self):
        with patch.object(app.urllib.request,'build_opener') as opener, patch.object(app.json,'load',return_value={'data':[{'id':'test-model'}]}):
            result=app.validate_connection({'key':'TEST ONLY KEY','base':'https://api.openai.com/v1','model':'test-model'})
        request=opener.return_value.open.call_args.args[0]
        self.assertIsNone(request.data);self.assertEqual(request.full_url,'https://api.openai.com/v1/models');self.assertTrue(result['listed_model_available']);self.assertEqual(result['reviews_sent'],0)
    def test_extraction_rejects_suggestions_in_first_stage(self):
        a=self.aspect();a['recommendation_kind']='AI推导建议';a['recommendation']='TEST ONLY';a['rationale']='TEST ONLY'
        with self.assertRaises(ValueError):app.check_analysis({'uncertainties':[],'review_note':'','aspects':[a]},{'text':'TEST ONLY alpha'})


    def test_upstream_error_stops_remaining_requests(self):
        d=self.fixture();i=app.uid();app.save(app.run_path(i),{'id':i,'review_ids':[x['id'] for x in d['reviews']],'results':[],'edits':[]})
        error=app.ModelOutputError('TEST upstream forbidden','',{'http_status':502,'usage':None})
        with patch.object(app,'call_model',side_effect=error) as call:
            app.worker(i,d,'TEST ONLY KEY','https://example.invalid','test','responses')
        r=app.load(app.run_path(i));self.assertEqual(call.call_count,1);self.assertEqual(app.statistics(r)['not_attempted_reviews'],1)
    def test_no_valid_extractions_cannot_generate_summary(self):
        d,r,a=self.run_fixture();r['status']='partial_or_failed';r['results']=[{'review_id':x['id'],'status':'failed'} for x in d['reviews']];app.save(app.run_path(r['id']),r)
        with self.assertRaises(ValueError):app.summarize_run(r['id'])


    def test_mechanical_aliases_do_not_rewrite_claims(self):
        a=self.aspect();a['polarity']='负向';del a['confidence'];original=a['claim'];result,changes=app.normalize_analysis({'aspects':[a],'uncertainties':[],'review_note':''},{'text':'TEST ONLY alpha'})
        self.assertEqual(result['aspects'][0]['polarity'],'槽点');self.assertEqual(result['aspects'][0]['confidence'],'未提供');self.assertEqual(result['aspects'][0]['claim'],original);self.assertEqual(len(changes),2);self.assertNotIn('confidence',a)
    def test_uncertainty_location_uses_exact_source_matches(self):
        result,changes=app.normalize_analysis({'aspects':[],'uncertainties':[{'question':'TEST','reason':'TEST','evidence':'TEST ONLY alpha'}],'review_note':''},{'text':'TEST ONLY alpha','title':'TEST ONLY alpha'})
        self.assertEqual(changes[0]['matching_fields'],['text','title']);self.assertEqual(result['uncertainties'][0]['evidence_field'],'text')
    def test_normalization_does_not_hide_unrecognized_fields(self):
        a=self.aspect();a['invented_field']='TEST';result,changes=app.normalize_analysis({'aspects':[a],'uncertainties':[],'review_note':''},{'text':'TEST ONLY alpha'})
        with self.assertRaises(ValueError):app.check_analysis(result,{'text':'TEST ONLY alpha'})

    def test_separate_experience_groups_and_no_approval_gate(self):
        d,r,a=self.run_fixture()
        aspects=r['results'][0]['analysis']['aspects']
        aspects[:]=[dict(a,id=app.uid(),experience=e) for e in app.EXPERIENCES+[app.LEGACY_EXPERIENCE]]
        s=app.statistics(r)
        self.assertEqual(len(s['themes']),1)
        self.assertEqual(s['themes'][0]['count'],1)
        self.assertFalse(s['human_review_required_to_view'])
        groups={x['key']:x for x in s['experience_groups']}
        self.assertEqual(groups['unknown']['aspect_count'],2)
        for k in ['actual','expectation','concern','reported']:self.assertEqual(groups[k]['review_count'],1)
        self.assertEqual(s['excluded_aspects'],5)

    def test_expectation_positive_is_not_experienced_benefit(self):
        d,r,a=self.run_fixture()
        r['results'][0]['analysis']['aspects']=[dict(a,experience='用户期望')]
        self.assertEqual(app.statistics(r)['themes'],[])
        self.assertEqual(app.experience_group(dict(a,experience='担心或预期')),'unknown')
        self.assertEqual(app.experience_group(dict(a,polarity='信息不足')),'unknown')

    def test_unconfirmed_summary_can_be_viewed_and_keeps_uncertainty(self):
        d,r,a=self.run_fixture();r['status']='completed';r['human_reviews']=[]
        r['results'][0]['analysis']['uncertainties']=[{'question':'TEST ONLY unknown'}]
        app.save(app.run_path(r['id']),r)
        summary=app.summarize_run(r['id'])
        self.assertTrue(summary['provisional']);self.assertEqual(summary['human_reviews'],[])
        self.assertEqual(summary['statistics']['experience_groups'][-1]['review_count'],1)
        self.assertTrue((app.SUMMARIES/(r['id']+'.json')).exists())

    def test_new_experience_edit_is_optional_overlay(self):
        d,r,a=self.run_fixture()
        updated=app.edit_run(r['id'],a['id'],{'experience':'用户期望'})
        self.assertEqual(updated['results'][0]['analysis']['aspects'][0]['experience'],'实际经历')
        self.assertEqual(app.effective(updated)[0]['analysis']['aspects'][0]['experience'],'用户期望')

    def test_major_category_synonyms_dedup_and_all_sources(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='cleaning',theme_key='clean-ease',topic='清洁维护',claim='本产品清理起来很容易。'),dict(a,id=app.uid(),major_category='cleaning',theme_key='clean-ease',topic='清洗',claim='本产品容易清洁。')]
        r['results'][1]={'review_id':d['reviews'][1]['id'],'status':'completed','analysis':{'aspects':[dict(a,id=app.uid(),major_category='cleaning',theme_key='clean-ease',topic='清洁',claim='清洁很方便。')],'uncertainties':[]}}
        summary=app.thematic_summary(r);cat=summary['categories'][0];group=cat['groups'][0]
        self.assertEqual(summary['analyzed_count'],2);self.assertEqual(len(cat['groups']),1);self.assertEqual(group['count'],2);self.assertEqual(group['percent'],100);self.assertEqual(len(group['sources']),3)

    def test_contrary_component_cleaning_not_cancelled(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='cleaning',theme_key='clean-ease',topic='清洁维护',claim='整体容易清洁。'),dict(a,id=app.uid(),major_category='cleaning',theme_key='component-cleaning',topic='部件清洁',polarity='槽点',claim='某部件难清洗。')]
        cat=app.thematic_summary(r)['categories'][0]
        self.assertEqual(cat['positive_count'],1);self.assertEqual(cat['negative_count'],1);self.assertEqual(cat['count'],1);self.assertEqual(len(cat['groups']),2)

    def test_behavior_is_separate_and_unknown_topic_not_forced(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),topic='退货',polarity='槽点'),dict(a,id=app.uid(),topic='TEST ONLY unseen label')]
        summary=app.thematic_summary(r)
        self.assertEqual(summary['behavior_review_count'],1);self.assertEqual(summary['categories'][0]['key'],'other');self.assertEqual(len(summary['categories']),1)

    def test_context_signature_prevents_stale_annotation(self):
        d,r,a=self.run_fixture();import thematic
        rules={'aspects':{a['id']:{'source_signature':thematic.signature(a),'changes':{'_bucket':'context'},'reason':'TEST ONLY contextual qualification'}}}
        first=thematic.aggregate(r,app.effective(r),rules)
        self.assertEqual(first['categories'][0]['positive_count'],1) # a duplicate remains an independent uncorrected extraction
        self.assertEqual(len(first['context_corrections']),1)
        a['claim']='TEST ONLY changed by user'
        second=thematic.aggregate(r,app.effective(r),rules)
        self.assertEqual(second['context_corrections'],[])

    def test_export_includes_traceable_aggregation(self):
        d,r,a=self.run_fixture();z=zipfile.ZipFile(io.BytesIO(app.export_zip(d,r)))
        summary=json.loads(z.read('theme_aggregation.json'))
        self.assertEqual(summary['categories'][0]['groups'][0]['sources'][0]['aspect_id'],a['id'])

    def test_qualified_heating_is_context_not_two_benefits(self):
        import thematic
        d,r,a=self.run_fixture();a.update(topic='加热效果',major_category='cooking',theme_key='preheat-start');b=dict(a,id=app.uid(),topic='整体表现');r['results'][0]['analysis']['aspects']=[a,b]
        rules={'aspects':{x['id']:{'source_signature':thematic.signature(x),'changes':{'_bucket':'context','claim':'TEST ONLY qualified paragraph'},'reason':'TEST ONLY preserve full context'} for x in [a,b]}}
        summary=thematic.aggregate(r,app.effective(r),rules);cat=summary['categories'][0]
        self.assertEqual(cat['positive_count'],0);self.assertEqual(len(cat['groups']),1);self.assertEqual(cat['groups'][0]['count'],1);self.assertEqual(len(cat['groups'][0]['sources']),2)

    def test_optional_major_category_edit_preserves_original(self):
        d,r,a=self.run_fixture();updated=app.edit_run(r['id'],a['id'],{'major_category':'cleaning'})
        self.assertEqual(updated['results'][0]['analysis']['aspects'][0]['major_category'],'other')
        self.assertIn('cleaning',[c['key'] for c in app.thematic_summary(updated)['categories']])
        with self.assertRaises(ValueError):app.edit_run(r['id'],a['id'],{'major_category':'invented'})

    def test_neutral_background_and_task_do_not_become_benefits(self):
        d,r,a=self.run_fixture()
        r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='capacity',theme_key='household',topic='人数',feedback_kind='使用背景',polarity='中立',claim='TEST ONLY 我们家两个人用'),dict(a,id=app.uid(),major_category='cooking',theme_key='tasks',topic='支持的烹饪任务',feedback_kind='用途描述',polarity='中立',claim='TEST ONLY 可以做薯条和鸡翅')]
        summary=app.thematic_summary(r)
        self.assertEqual(len(summary['scenarios']),1);self.assertEqual(len(summary['categories']),1)
        c=summary['categories'][0];self.assertEqual(c['neutral_count'],1);self.assertEqual(c['positive_count'],0);self.assertEqual(c['negative_count'],0)
        self.assertEqual(app.statistics(r)['themes'],[])

    def test_opposite_same_theme_only_is_a_conflict(self):
        d,r,a=self.run_fixture()
        r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='cooking',theme_key='preheat-start',topic='预热',polarity='槽点',claim='TEST ONLY 预热慢但成品好'),dict(a,id=app.uid(),major_category='cooking',theme_key='crispness',topic='酥脆度',claim='TEST ONLY 外酥里嫩')]
        cat=app.thematic_summary(r)['categories'][0]
        self.assertEqual(cat['conflict_theme_keys'],[]);self.assertNotIn('相反评价',cat['judgment']);self.assertEqual(cat['positive_count'],1);self.assertEqual(cat['negative_count'],1)
        r['results'][0]['analysis']['aspects'].append(dict(a,id=app.uid(),major_category='cooking',theme_key='crispness',topic='酥脆度',polarity='槽点',claim='TEST ONLY 不酥脆'))
        cat=app.thematic_summary(r)['categories'][0]
        self.assertEqual(cat['conflict_theme_keys'],['crispness']);self.assertIn('存在不同评价',cat['judgment'])

    def test_ambiguous_fit_is_not_invented_capacity_or_function(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,topic='烹饪方式适配',claim='TEST ONLY 不适合我的烹饪方式',polarity='槽点')]
        c=app.thematic_summary(r)['categories'][0]
        self.assertEqual(c['key'],'other');self.assertEqual(c['groups'][0]['sources'][0]['claim'],'TEST ONLY 不适合我的烹饪方式')
        self.assertTrue(c['judgment'].startswith('有一条评论'))

    def test_basket_object_does_not_determine_category(self):
        d,r,a=self.run_fixture()
        r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category=c,theme_key='custom:'+c,topic='炸篮',claim=claim) for c,claim in [('capacity','TEST ONLY 炸篮太小'),('cleaning','TEST ONLY 炸篮难洗'),('reliability','TEST ONLY 炸篮闭合困难')]]
        self.assertEqual({c['key'] for c in app.thematic_summary(r)['categories']},{'capacity','cleaning','reliability'})

    def test_uncertain_neutral_keeps_unknown_bucket(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,polarity='中立',experience='无法判断')]
        c=app.thematic_summary(r)['categories'][0];self.assertEqual(c['neutral_count'],0);self.assertEqual(c['groups'][0]['bucket'],'unknown')

    def test_background_and_known_theme_contract_validation(self):
        a=self.aspect();a.update(feedback_kind='使用背景',polarity='优点')
        with self.assertRaises(ValueError):app.check_analysis({'review_note':'','uncertainties':[],'aspects':[a]},{'text':'TEST ONLY alpha'})
        a.update(feedback_kind='产品反馈',theme_key='startup-noise',major_category='reliability')
        with self.assertRaises(ValueError):app.check_analysis({'review_note':'','uncertainties':[],'aspects':[a]},{'text':'TEST ONLY alpha'})

    def test_overall_and_behavior_do_not_populate_experience_categories(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),feedback_kind='整体评价',claim='TEST ONLY 很满意'),dict(a,id=app.uid(),feedback_kind='行为或意向',topic='推荐',claim='TEST ONLY 愿意推荐')]
        summary=app.thematic_summary(r);self.assertEqual(summary['categories'],[]);self.assertEqual(len(summary['overall_evaluations']),1);self.assertEqual(len(summary['behaviors']),1);self.assertEqual(app.statistics(r)['themes'],[])

    def test_manual_category_override_does_not_silently_erase_context(self):
        import thematic
        d,r,a=self.run_fixture();rules={'aspects':{a['id']:{'source_signature':thematic.signature(a),'changes':{'_bucket':'context','major_category':'cooking'},'reason':'TEST ONLY full context'}}}
        r['edits']=[{'aspect_id':a['id'],'changes':{'major_category':'cleaning'}}]
        summary=thematic.aggregate(r,app.effective(r),rules)
        corrected=next(c for c in summary['categories'] if c['key']=='cleaning')
        self.assertEqual(corrected['positive_count'],0);self.assertEqual(corrected['groups'][0]['bucket'],'context')

    def test_counts_deduplicate_repeated_review_results(self):
        d,r,a=self.run_fixture();r['results'].append(r['results'][0])
        self.assertEqual(app.statistics(r)['completed_reviews'],1)
        summary=app.thematic_summary(r);self.assertEqual(summary['analyzed_count'],1);self.assertEqual(summary['categories'][0]['groups'][0]['count'],1)

    def guided_dataset(self,n=50):
        return app.import_csv('text\n'+'\n'.join('TEST ONLY workflow '+str(i) for i in range(n)),'TEST ONLY WORKFLOW')
    def guided_run(self,d):
        with patch.object(app.threading,'Thread'):
            return app.create_run(d,{'workflow':'guided','key':'TEST ONLY','base':'https://example.invalid','model':'TEST','mode':'responses'})
    def model_success(self,raw,*args,**kwargs):
        return {'review_note':'TEST ONLY','aspects':[dict(self.aspect(quote=raw['text']))],'uncertainties':[]},{'usage':{'input_tokens':2,'output_tokens':3,'total_tokens':5},'raw_output':'TEST ONLY SAVED OUTPUT'}
    def gate_success(self,*args):
        return {'status':'passed','checks':[],'method':'TEST ONLY','raw_output':'TEST ONLY','api':{'usage':{'input_tokens':10,'output_tokens':5,'total_tokens':15}}}
    def test_guided_trial_failure_never_runs_full_batch(self):
        import workflow
        d=self.guided_dataset();r=self.guided_run(d)
        with patch.object(app,'call_model',side_effect=ValueError('TEST ONLY invalid')),patch.object(workflow,'audit_trial') as audit:workflow.execute(app,r['id'],d,'TEST ONLY')
        r=app.load(app.run_path(r['id']));self.assertEqual(len(r['results']),8);self.assertEqual(r['phase'],'trial_failed');audit.assert_not_called()
        report=app.thematic_summary(r)['report'];self.assertEqual(report['success'],0);self.assertEqual(report['failed'],8);self.assertEqual(report['unattempted'],42)
    def test_guided_success_reuses_same_version_and_audit(self):
        import workflow
        d=self.guided_dataset();r=self.guided_run(d)
        with patch.object(app,'call_model',side_effect=self.model_success) as model,patch.object(workflow,'audit_trial',side_effect=self.gate_success) as audit:
            workflow.execute(app,r['id'],d,'TEST ONLY');self.assertEqual(model.call_count,50);self.assertEqual(audit.call_count,1)
            second=self.guided_run(d);workflow.execute(app,second['id'],d,'TEST ONLY');self.assertEqual(model.call_count,50);self.assertEqual(audit.call_count,1)
        second=app.load(app.run_path(second['id']));self.assertEqual(second['status'],'completed');self.assertEqual(len(second['results']),50);self.assertEqual(app.usage_report(second)['tokens_reported']['total_tokens'],0);self.assertEqual(app.usage_report(second)['reused_reviews'],50)
        self.assertIn('完整批次报告',app.thematic_summary(second)['report']['title'])
    def test_guided_retry_only_failed_after_full_phase(self):
        import workflow
        d=self.guided_dataset();r=self.guided_run(d);bad=d['reviews'][12]['raw']['text']
        def partial(raw,*args):
            if raw['text']==bad:raise ValueError('TEST ONLY transient')
            return self.model_success(raw,*args)
        with patch.object(app,'call_model',side_effect=partial),patch.object(workflow,'audit_trial',side_effect=self.gate_success):workflow.execute(app,r['id'],d,'TEST ONLY')
        first=app.load(app.run_path(r['id']));self.assertEqual(first['phase'],'full_batch_partial');self.assertEqual(app.statistics(first)['completed_reviews'],49)
        second=self.guided_run(d)
        with patch.object(app,'call_model',side_effect=self.model_success) as model,patch.object(workflow,'audit_trial') as audit:workflow.execute(app,second['id'],d,'TEST ONLY');self.assertEqual(model.call_count,1);audit.assert_not_called()
        self.assertEqual(app.statistics(app.load(app.run_path(second['id'])))['completed_reviews'],50)
    def test_semantic_gate_failure_blocks_full_and_bad_cache(self):
        import workflow
        d=self.guided_dataset();r=self.guided_run(d)
        def gate(*args):return dict(self.gate_success(),status='needs_fix',checks=[{'review_id':d['reviews'][0]['id'],'verdict':'needs_fix','reason':'TEST ONLY unsupported'}])
        with patch.object(app,'call_model',side_effect=self.model_success),patch.object(workflow,'audit_trial',side_effect=gate):workflow.execute(app,r['id'],d,'TEST ONLY')
        r=app.load(app.run_path(r['id']));self.assertEqual(r['phase'],'trial_needs_fix');self.assertEqual(len(r['results']),8);self.assertNotIn(d['reviews'][0]['id'],workflow.cache(app,d,r['analysis_signature']))
    def test_version_signature_changes_with_prompt_or_provider(self):
        import workflow
        d=self.guided_dataset(8);config={'base':'https://example.invalid','model':'test','mode':'responses'};sig=workflow.fingerprint(app,d,config)
        with patch.object(app,'PROMPT',app.PROMPT+' TEST ONLY changed'):self.assertNotEqual(sig,workflow.fingerprint(app,d,config))
        self.assertNotEqual(sig,workflow.fingerprint(app,d,dict(config,model='other')))
    def test_core_merges_related_topics_without_summing_mentions(self):
        import insights
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='usability',theme_key='operation-ease',topic='操作',claim='TEST ONLY 容易操作'),dict(a,id=app.uid(),major_category='usability',theme_key='turning',topic='翻面',claim='TEST ONLY 无需翻面')]
        report=app.thematic_summary(r)['report'];self.assertEqual(len(report['keeps']),1);self.assertEqual(report['keeps'][0]['count'],1);self.assertEqual(len(report['keeps'][0]['sources']),2);self.assertEqual(report['keeps'][0]['support_label'],'个别反馈');self.assertIn('尚非完整批次',report['title'])
    def test_priority_uses_impact_and_neutral_does_not_become_core(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='reliability',theme_key='closure',topic='闭合',polarity='槽点'),dict(a,id=app.uid(),major_category='environment',theme_key='startup-noise',topic='噪音',polarity='槽点'),dict(a,id=app.uid(),polarity='中立')]
        report=app.thematic_summary(r)['report'];self.assertEqual(len(report['issues']),2);self.assertEqual(report['issues'][0]['category_key'],'reliability');self.assertEqual(report['keeps'],[])
        self.assertEqual(report['issues'][0]['recommendation']['review_ids'],report['issues'][0]['review_ids'])
    def test_report_export_contains_evidence_and_scope(self):
        d,r,a=self.run_fixture();z=zipfile.ZipFile(io.BytesIO(app.export_zip(d,r)));report=z.read('batch_report.md').decode();self.assertIn(a['evidence'],report);self.assertIn('尚未验证的原因假设',report);self.assertIn('成功 1',report)

    def test_guided_duplicate_start_returns_active_run(self):
        d=self.guided_dataset();r=self.guided_run(d);other=self.guided_run(d)
        self.assertEqual(other['id'],r['id']);self.assertEqual(len(list(app.RUNS.glob('*.json'))),1)

    def test_other_unit_negative_background_is_allowed_but_not_counted(self):
        a=self.aspect(subject='其他产品',polarity='槽点');a['feedback_kind']='使用背景'
        app.check_analysis({'review_note':'','aspects':[a],'uncertainties':[]},{'text':'TEST ONLY alpha'})
    def test_guided_repair_only_flagged_preserves_history_and_usage(self):
        import workflow
        d=self.guided_dataset();r=self.guided_run(d)
        gate=dict(self.gate_success(),status='needs_fix',checks=[{'review_id':d['reviews'][0]['id'],'verdict':'needs_fix','reason':'TEST ONLY keep context'}])
        with patch.object(app,'call_model',side_effect=self.model_success) as model,patch.object(workflow,'audit_trial',side_effect=[gate,self.gate_success()]):workflow.execute(app,r['id'],d,'TEST ONLY')
        r=app.load(app.run_path(r['id']));self.assertEqual(r['status'],'completed');self.assertEqual(model.call_count,51);self.assertEqual(len(r['attempt_history']),1);self.assertEqual(len(r['auxiliary_requests']),3);self.assertEqual(app.usage_report(r)['tokens_reported']['total_tokens'],285)
    def test_expectation_labeled_as_intent_still_not_actual_behavior(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,feedback_kind='行为或意向',experience='用户期望',topic='希望吃得健康')]
        summary=app.thematic_summary(r);self.assertEqual(summary['behaviors'],[]);self.assertEqual(summary['categories'][0]['groups'][0]['bucket'],'expectation')

    def test_audit_prompt_includes_actual_taxonomy_boundaries(self):
        import workflow
        d,r,a=self.run_fixture();results=[r['results'][0]];checks={'checks':[{'review_id':results[0]['review_id'],'verdict':'pass','reason':'TEST ONLY'}]}
        data={'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(checks)}]}],'usage':{'total_tokens':1}}
        with patch.object(workflow.urllib.request,'build_opener') as opener,patch.object(workflow.json,'load',return_value=data):workflow.audit_trial(app,d,results,'TEST ONLY','https://example.invalid','TEST','responses')
        payload=json.loads(opener.return_value.open.call_args.args[0].data)
        self.assertIn(app.thematic.CONFIG['categories']['reliability']['scope'],payload['instructions']);self.assertIn('部件设计',payload['instructions'])
    def test_adjudication_is_bound_to_outputs_and_taxonomy(self):
        import workflow,hashlib
        d=self.guided_dataset(8);r=self.guided_run(d);r['results']=[{'review_id':x['id'],'raw_output':'TEST ONLY '+str(i)} for i,x in enumerate(d['reviews'])]
        r['quality_gate']={'adjudication':{'verdict':'pass','analysis_signature':r['analysis_signature'],'taxonomy_hash':hashlib.sha256(json.dumps(app.thematic.CONFIG,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'output_hashes':{x['review_id']:hashlib.sha256(x['raw_output'].encode()).hexdigest() for x in r['results']}}}
        self.assertTrue(workflow.valid_adjudication(app,r));r['results'][0]['raw_output']='TEST ONLY changed';self.assertFalse(workflow.valid_adjudication(app,r))

    def test_daily_small_upload_runs_without_eight_or_human_gate(self):
        import workflow
        d=self.guided_dataset(3)
        with patch.object(app.threading,'Thread'):r=app.create_run(d,{'workflow':'daily','key':'TEST ONLY','base':'https://example.invalid','model':'TEST','mode':'responses'})
        self.assertEqual(r['trial_review_ids'],[]);self.assertEqual(len(r['review_ids']),3)
        with patch.object(app,'call_model',side_effect=self.model_success),patch.object(workflow,'audit_trial') as audit:workflow.execute(app,r['id'],d,'TEST ONLY');audit.assert_not_called()
        r=app.load(app.run_path(r['id']));self.assertEqual(r['status'],'completed');self.assertEqual(r['human_reviews'],[]);self.assertEqual(app.thematic_summary(r)['report']['success'],3)
    def test_daily_reuses_completed_trial_without_new_trial_or_audit(self):
        import workflow
        d=self.guided_dataset();r=self.guided_run(d)
        with patch.object(app,'call_model',side_effect=self.model_success),patch.object(workflow,'audit_trial',side_effect=self.gate_success):workflow.execute(app,r['id'],d,'TEST ONLY')
        with patch.object(app.threading,'Thread'):second=app.create_run(d,{'workflow':'daily','key':'TEST ONLY','base':'https://example.invalid','model':'TEST','mode':'responses'})
        with patch.object(app,'call_model') as model,patch.object(workflow,'audit_trial') as audit:workflow.execute(app,second['id'],d,'TEST ONLY');model.assert_not_called();audit.assert_not_called()
        self.assertEqual(app.load(app.run_path(second['id']))['status'],'completed')

    def test_future_purchase_is_behavior_without_assuming_purchase_occurred(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='other',theme_key='repurchase-intent',feedback_kind='行为或意向',topic='为生日再买一台',experience='无法判断')]
        agg=app.thematic_summary(r);self.assertEqual(agg['categories'],[]);self.assertEqual(len(agg['behaviors']),1);self.assertIn('不据此推断',agg['behaviors'][0]['status']);self.assertEqual(agg['report']['keeps'],[])
    def test_return_with_topic_variant_keeps_actual_action(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),theme_key='return',feedback_kind='行为或意向',topic='退货行为')]
        self.assertEqual(app.thematic_summary(r)['behaviors'][0]['status'],'已发生的退货行为')
    def test_core_conditions_are_concise_and_full_sources_preserved(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='cleaning',theme_key='clean-ease',scenario='TEST CONDITION '+str(i)) for i in range(12)]
        f=app.thematic_summary(r)['report']['keeps'][0];self.assertEqual(f['count'],1);self.assertEqual(len(f['sources']),12);self.assertIn('TEST CONDITION 1',f['explanation']);self.assertNotIn('TEST CONDITION 2',f['explanation'])
    def test_unrelated_uncertainty_does_not_reduce_explicit_finding_priority(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='reliability',theme_key='closure',polarity='槽点',confidence='高')];r['results'][0]['analysis']['uncertainties']=[{'question':'TEST ONLY unrelated cause unknown'}]
        f=app.thematic_summary(r)['report']['issues'][0];self.assertIn('明确表达',f['priority']['evidence'])

    def test_daily_cache_preserves_optional_edits_and_signed_context(self):
        import workflow,thematic
        d=self.guided_dataset(3)
        with patch.object(app.threading,'Thread'):first=app.create_run(d,{'workflow':'daily','key':'TEST ONLY','base':'https://example.invalid','model':'TEST','mode':'responses'})
        with patch.object(app,'call_model',side_effect=self.model_success):workflow.execute(app,first['id'],d,'TEST ONLY')
        first=app.load(app.run_path(first['id']));a=first['results'][0]['analysis']['aspects'][0];b=first['results'][1]['analysis']['aspects'][0]
        first['edits']=[{'aspect_id':a['id'],'changes':{'polarity':'中立'}}];app.save(app.run_path(first['id']),first)
        with patch.object(app,'ROOT',self.p):
            folder=self.p/'curation';folder.mkdir();app.save(folder/(first['id']+'.json'),{'aspects':{b['id']:{'source_signature':thematic.signature(b),'changes':{'polarity':'信息不足'},'reason':'TEST ONLY signed context'}}})
            with patch.object(app.threading,'Thread'):second=app.create_run(d,{'workflow':'daily','key':'TEST ONLY','base':'https://example.invalid','model':'TEST','mode':'responses'})
            with patch.object(app,'call_model') as model:workflow.execute(app,second['id'],d,'TEST ONLY');model.assert_not_called()
            second=app.load(app.run_path(second['id']));self.assertEqual(second['results'][0]['analysis']['aspects'][0]['polarity'],a['polarity']);self.assertEqual(app.effective(second)[0]['analysis']['aspects'][0]['polarity'],'中立');self.assertEqual(app.aggregation_effective(second)[1]['analysis']['aspects'][0]['polarity'],'信息不足')

    def test_expected_use_benefit_is_kept_outside_actual_pros(self):
        d,r,a=self.run_fixture();v=json.loads(json.dumps(self.model_success(d['reviews'][0]['raw'])[0]));v['aspects'][0].update(major_category='other',theme_key='health-expectation',feedback_kind='用途描述',experience='用户期望',polarity='优点')
        app.check_analysis(v,d['reviews'][0]['raw']);v['aspects'][0]['id']=app.uid();r['results'][0]['analysis']=v
        report=app.thematic_summary(r)['report'];self.assertEqual(report['keeps'],[]);self.assertEqual(report['consumer_expectations'][0]['count'],1)

    def test_export_effective_json_and_csv_apply_aggregation_corrections(self):
        d,r,a=self.run_fixture();rows=app.effective(r);rows[0]['analysis']['aspects'][0]['claim']='TEST ONLY corrected effective claim'
        with patch.object(app,'aggregation_effective',return_value=rows):
            archive=zipfile.ZipFile(io.BytesIO(app.export_zip(d,r)));self.assertIn('TEST ONLY corrected effective claim',archive.read('analysis_effective.json').decode());self.assertIn('TEST ONLY corrected effective claim',archive.read('analysis.csv').decode());self.assertNotIn('TEST ONLY corrected effective claim',archive.read('analysis_original_and_edits.json').decode());self.assertNotIn('均需人工复核',archive.read('README.txt').decode())
    def test_partial_success_can_summarize_while_remaining_analysis_runs(self):
        d,r,a=self.run_fixture();r['status']='running';app.save(app.run_path(r['id']),r)
        summary=app.summarize_run(r['id']);self.assertGreater(summary['statistics']['completed_reviews'],0);self.assertIn('可选操作',summary['note'])

    def test_quote_case_alignment_is_unique_and_logged(self):
        raw={'text':'TEST ONLY original','title':'Easy to use and easy clean up!'};value={'aspects':[{'evidence':'easy to use','evidence_field':'title'}],'uncertainties':[]}
        normalized,changes=app.normalize_analysis(value,raw);self.assertEqual(normalized['aspects'][0]['evidence'],'Easy to use');self.assertEqual(value['aspects'][0]['evidence'],'easy to use');self.assertTrue(any(c['rule']=='unique_case_only_alignment_to_original_source' for c in changes))
    def test_ambiguous_quote_case_is_not_silently_aligned(self):
        normalized,changes=app.normalize_analysis({'aspects':[{'evidence':'easy','evidence_field':'title'}]}, {'title':'Easy EASY'});self.assertEqual(normalized['aspects'][0]['evidence'],'easy');self.assertFalse(any(c['rule']=='unique_case_only_alignment_to_original_source' for c in changes))

    def test_complete_cache_materialization_never_calls_model_and_usage_dedups(self):
        import workflow
        d=self.guided_dataset(3)
        with patch.object(app.threading,'Thread'):first=app.create_run(d,{'workflow':'daily','key':'TEST ONLY','base':'https://example.invalid','model':'TEST','mode':'responses'})
        with patch.object(app,'call_model',side_effect=self.model_success):workflow.execute(app,first['id'],d,'TEST ONLY')
        with patch.object(app,'call_model') as model:second=workflow.materialize_cache(app,app.load(app.run_path(first['id'])));model.assert_not_called()
        self.assertEqual(second['status'],'completed');self.assertEqual(app.usage_report(second)['requests_finished'],0);lineage=app.usage_lineage(second);self.assertEqual(lineage['requests_attempted'],3);self.assertEqual(lineage['known_tokens']['total_tokens'],15)
    def test_incomplete_cache_cannot_be_marked_complete(self):
        import workflow
        d=self.guided_dataset(3)
        with patch.object(app.threading,'Thread'):first=app.create_run(d,{'workflow':'daily','key':'TEST ONLY','base':'https://example.invalid','model':'TEST','mode':'responses'})
        with self.assertRaises(ValueError):workflow.materialize_cache(app,first)

    def test_expected_feedback_never_uses_actual_experience_template(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='usability',theme_key='operation-ease',experience='用户期望',claim='TEST ONLY 希望操作更省事，但没有验证')]
        g=app.thematic_summary(r)['categories'][0]['groups'][0];self.assertEqual(g['bucket'],'expectation');self.assertIn('没有验证',g['description']);self.assertNotIn('日常操作容易上手',g['description'])
    def test_future_cooking_plan_is_intent_not_product_experience(self):
        d,r,a=self.run_fixture();r['results'][0]['analysis']['aspects']=[dict(a,id=app.uid(),major_category='other',theme_key='future-cooking-use',feedback_kind='行为或意向',experience='用户期望',claim='TEST ONLY 计划以后尝试做奶酪')]
        agg=app.thematic_summary(r);self.assertEqual(agg['categories'],[]);self.assertEqual(len(agg['behaviors']),1);self.assertEqual(agg['behaviors'][0]['experience'],'用户期望');self.assertEqual(agg['report']['keeps'],[])

if __name__=='__main__':unittest.main(verbosity=2)
