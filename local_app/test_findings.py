"""TEST ONLY development fixtures; never imported to the formal review library."""
import unittest,copy,json,io,zipfile
from unittest.mock import patch
import app,insights,test_app

class FocusedFindingsTests(unittest.TestCase):
    setUp=test_app.PipelineTests.setUp
    tearDown=test_app.PipelineTests.tearDown
    aspect=test_app.PipelineTests.aspect
    fixture=test_app.PipelineTests.fixture
    run_fixture=test_app.PipelineTests.run_fixture
    guided_dataset=test_app.PipelineTests.guided_dataset
    def batch(self,aspects_by_index,n=50):
        d=self.guided_dataset(n);rows=[]
        for i,row in enumerate(d['reviews']):
            aspects=[]
            for changes in aspects_by_index.get(i,[]):
                a=dict(self.aspect(quote=row['raw']['text']),id=app.uid());a.update(changes);aspects.append(a)
            rows.append({'review_id':row['id'],'status':'completed','analysis':{'review_note':'TEST ONLY','uncertainties':[],'aspects':aspects}})
        r={'id':app.uid(),'dataset_id':d['id'],'product':'TEST ONLY','status':'completed','prompt_version':app.PROMPT_VERSION,'review_ids':[row['id'] for row in d['reviews']],'results':rows,'edits':[],'human_reviews':[]}
        app.save(app.run_path(r['id']),r);return d,r,app.thematic_summary(r)['report']
    def test_positive_large_category_cannot_support_specific_negative(self):
        changes={i:[{'major_category':'cooking','theme_key':'air-fry-results','claim':'TEST ONLY tasty'}] for i in range(16)}
        changes[16]=[{'major_category':'cooking','theme_key':'surface-burning','polarity':'槽点','claim':'TEST ONLY top burnt'}]
        changes[17]=[{'major_category':'cooking','theme_key':'air-fry-results','polarity':'槽点','claim':'TEST ONLY dry','evidence':'dry'}]
        d,r,_=self.batch(changes)
        # Isolated semantic fixture: raw text supports the dryness word used by the conditional grouping.
        d['reviews'][17]['raw']['text']='dry';app.save(app.dataset_path(d['id']),d)
        p=app.thematic_summary(r)['report'];f=next(f for f in p['issues'] if f['family']=='overcooking')
        self.assertEqual((f['count'],f['positive_count'],f['negative_count']),(2,0,2));self.assertFalse(f['has_evaluation_difference']);self.assertEqual(len(p['keeps']),1);self.assertEqual(p['keeps'][0]['count'],16);self.assertTrue(set(f['review_ids']).isdisjoint(p['keeps'][0]['review_ids']))
    def test_under_cooking_not_forced_into_overcooking(self):
        d,r,p=self.batch({0:[{'major_category':'cooking','theme_key':'surface-burning','polarity':'槽点'}],1:[{'major_category':'cooking','theme_key':'air-fry-results','polarity':'槽点','evidence':'undercooked','claim':'TEST ONLY undercooked'}]})
        over=next(f for f in p['findings'] if f['family']=='overcooking');self.assertEqual(over['count'],1);self.assertNotIn('过干',over['title']);self.assertEqual(len(p['issues']),2)
    def test_overcooking_requires_each_member_to_support_group_meaning(self):
        d,r,p=self.batch({0:[{'major_category':'cooking','theme_key':'surface-burning','polarity':'槽点'}],1:[{'major_category':'cooking','theme_key':'air-fry-results','polarity':'槽点','evidence':'dry'}],2:[{'major_category':'cooking','theme_key':'air-fry-results','polarity':'槽点','evidence':'cold'}]})
        # A mixed broad group cannot be assumed all overcooked.
        self.assertEqual(next(f for f in p['findings'] if f['family']=='overcooking')['count'],1)
    def test_related_positive_benefit_union_not_addition(self):
        changes={i:[{'major_category':'usability','theme_key':'operation-ease'}] for i in range(15)}
        for i in range(10,22):changes.setdefault(i,[]).append({'major_category':'cooking','theme_key':'cooking-speed'})
        d,r,p=self.batch(changes);self.assertEqual(len(p['keeps']),1);f=p['keeps'][0];self.assertEqual(f['count'],22);self.assertEqual(sorted(c['count'] for c in f['contributions']),[12,15]);self.assertEqual(len(f['category_keys']),2)
    def test_rare_distinct_positive_stays_detail_not_collapsed_core(self):
        changes={i:[{'major_category':'cleaning','theme_key':'clean-ease'}] for i in range(18)}
        changes[20]=[{'major_category':'value','theme_key':'value-money'}]
        d,r,p=self.batch(changes);self.assertEqual(len(p['keeps']),1);self.assertEqual(p['keeps'][0]['count'],18);self.assertTrue(any(f['family']=='value-money' and not f['is_core'] for f in p['findings']))
    def test_single_use_blocking_problem_is_core_despite_frequency(self):
        d,r,p=self.batch({0:[{'major_category':'reliability','theme_key':'closure','polarity':'槽点'}]});self.assertEqual(len(p['issues']),1);self.assertEqual(p['issues'][0]['count'],1);self.assertIn('一条评论',p['issues'][0]['title'])
    def test_rare_minor_learning_problem_keeps_no_biggie_boundary_in_detail(self):
        d,r,p=self.batch({0:[{'major_category':'usability','theme_key':'time-temp-learning','polarity':'槽点','claim':'TEST ONLY 参数摸索，但问题不大'}]})
        self.assertEqual(p['issues'],[]);f=p['findings'][0];self.assertIn('问题不大',f['explanation']);self.assertNotIn('说明书有缺陷',f['title']);self.assertIn('不据试错自述认定',f['recommendation']['action'])
    def test_specific_speed_positive_has_no_cooking_defect_task(self):
        d,r,p=self.batch({0:[{'major_category':'cooking','theme_key':'cooking-speed'}]},n=1)
        a=p['theme_actions']['cooking|cooking-speed|actual|优点'];self.assertNotIn('成品问题',a['action']);self.assertIsNone(a['validation']);self.assertIsNone(a['missing']);self.assertNotIn('排查',p['keeps'][0]['recommendation']['action'])
    def test_cleaning_difficulty_not_canceled_by_other_positive_tasks(self):
        d,r,p=self.batch({0:[{'major_category':'cleaning','theme_key':'clean-ease','polarity':'槽点'},{'major_category':'cooking','theme_key':'cooking-speed'}]},n=1)
        f=p['issues'][0];self.assertEqual((f['positive_count'],f['negative_count']),(0,1));self.assertEqual(f['category_key'],'cleaning');self.assertFalse(f['has_evaluation_difference'])
    def test_narrow_comparison_counts_do_not_include_neighbor_theme(self):
        d,r,p=self.batch({0:[{'major_category':'cleaning','theme_key':'clean-ease'}],1:[{'major_category':'cleaning','theme_key':'clean-ease','polarity':'槽点'}],2:[{'major_category':'cleaning','theme_key':'oil-mess'}]},n=3)
        f=next(f for f in p['findings'] if f['has_evaluation_difference']);self.assertEqual(f['count'],2);self.assertEqual(f['positive_count'],1);self.assertEqual(f['negative_count'],1);self.assertEqual({insights.canonical(g['theme_key']) for g in f['groups']},{'clean-ease'})
    def test_neutral_expectation_unknown_and_reference_excluded_from_core(self):
        d,r,p=self.batch({0:[{'major_category':'cooking','theme_key':'cooking-speed','polarity':'中立'},{'major_category':'cooking','theme_key':'cooking-speed','experience':'用户期望'},{'major_category':'cooking','theme_key':'cooking-speed','experience':'无法判断'},{'major_category':'cooking','theme_key':'cooking-speed','subject':'其他产品'}]},n=1);self.assertEqual(p['findings'],[])
    def test_safety_pending_support_excludes_actual_positive(self):
        d,r,p=self.batch({0:[{'major_category':'reliability','theme_key':'basket-heating-control','experience':'担心','polarity':'槽点','evidence':'could cause a fire'}],1:[{'major_category':'reliability','theme_key':'basket-heating-control'}]})
        f=p['issues'][0];self.assertEqual((f['count'],f['positive_count'],f['negative_count'],f['pending_count']),(1,0,0,1));self.assertEqual(p['negative_review_count'],0)
    def test_concise_and_full_reports_share_identical_narrative(self):
        d,r,p=self.batch({0:[{'major_category':'reliability','theme_key':'closure','polarity':'槽点'}]},n=1)
        brief=insights.markdown(p,False);full=insights.markdown(p,True);self.assertTrue(full.startswith(brief));self.assertNotIn('归纳相近含义',full);self.assertNotIn('有评论认可：评论者认为',full);self.assertNotIn('<details>',brief);self.assertIn('<details>',full);self.assertIn('TEST ONLY workflow 0',full);self.assertEqual(full.count('仅描述当前非随机导入样本'),1)
    def test_brief_in_zip_matches_server_shared_renderer(self):
        d,r,p=self.batch({0:[{'major_category':'reliability','theme_key':'closure','polarity':'槽点'}]},n=1)
        z=zipfile.ZipFile(io.BytesIO(app.export_zip(d,r)));self.assertEqual(z.read('batch_brief.md').decode(),app.thematic_summary(r)['report']['brief_markdown'])
    def test_history_timing_not_recovered_from_summary_creation_or_mtime(self):
        d,r,p=self.batch({},n=1);r.update(created_at='2020-01-01T00:00:00+00:00',finished_at='2020-01-01T00:01:00+00:00',phase='trial_failed',workflow='guided_batch_v1');app.save(app.run_path(r['id']),r)
        import performance
        row=performance.historical_timings(app,d['id'])[0];self.assertEqual(row['extraction_stage_wall_seconds'],60);self.assertIsNone(row['aggregation_seconds']);self.assertIsNone(row['end_to_end_including_aggregation_seconds']);self.assertEqual(row['new_model_requests'],1);self.assertEqual(row['reused_reviews'],0)

if __name__=='__main__':unittest.main()
