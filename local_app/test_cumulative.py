"""TEST ONLY independent fixtures, never imported into research data."""
import unittest,copy,json,io,zipfile
from unittest.mock import patch
import app,cumulative,test_app
class CumulativeTests(unittest.TestCase):
    setUp=test_app.PipelineTests.setUp
    tearDown=test_app.PipelineTests.tearDown
    aspect=test_app.PipelineTests.aspect
    def batch(self,ids,stamp='1',fail=(),version=None,product='TEST_ONLY',asin='TEST_ASIN'):
        text='text,review_id,source,asin\n'+''.join('TEST ONLY '+i+','+i+',TEST_SOURCE,'+asin+'\n' for i in ids)
        d=app.import_csv(text,product,'TEST_'+stamp+'.csv');d['created_at']=stamp;app.save(app.dataset_path(d['id']),d)
        r=dict(id=app.uid(),dataset_id=d['id'],product=product,created_at=stamp,status='completed',model='TEST_MODEL',mode='responses',prompt_version=version or app.PROMPT_VERSION,review_ids=[x['id'] for x in d['reviews']],edits=[],human_reviews=[],results=[])
        for i,row in zip(ids,d['reviews']):
            a=self.aspect(quote=row['raw']['text']);a.update(id=app.uid(),major_category='cleaning',theme_key='clean-ease',topic='清理省事')
            r['results'].append(dict(review_id=row['id'],status='failed' if i in fail else 'completed',error='TEST FAILURE' if i in fail else '',analysis={'aspects':[] if i in fail else [a],'uncertainties':[]}))
        app.save(app.run_path(r['id']),r);return d,r
    def cumulative(self):
        with patch.object(app,'call_model',side_effect=AssertionError('No model call allowed')):cumulative.refresh(app)
        d=next(app.load(p) for p in app.DATA.glob('dataset_*.json') if app.load(p).get('derived_kind'));r=max([app.load(p) for p in app.RUNS.glob('*.json') if app.load(p).get('derived_kind')],key=lambda r:r['created_at']);return d,r
    def test_stable_ids_dedup_repeat_import_and_reaggregate_union(self):
        a,ra=self.batch(['A','B']);b,rb=self.batch(['A','C'],'2',fail=['C']);before=app.run_path(ra['id']).read_bytes();d,r=self.cumulative();agg=app.thematic_summary(r)
        self.assertEqual((len(d['reviews']),agg['analyzed_count'],app.statistics(r)['failed_reviews']),(3,2,1));self.assertEqual(d['cumulative']['duplicate_count'],1);self.assertEqual(agg['categories'][0]['groups'][0]['count'],2);self.assertTrue(all(s['batch_origins'] for s in agg['categories'][0]['groups'][0]['sources']));self.assertEqual(app.run_path(ra['id']).read_bytes(),before);self.assertEqual(app.usage_report(r)['requests_finished'],0)
    def test_latest_failed_correction_does_not_resurrect_old_output(self):
        a,ra=self.batch(['A']);b,rb=self.batch(['B'],'2');new=copy.deepcopy(rb);new.update(id=app.uid(),created_at='3');new['results'][0].update(status='failed',error='TEST corrected invalid quote');app.save(app.run_path(new['id']),new);d,r=self.cumulative();self.assertEqual(app.statistics(r)['completed_reviews'],1);self.assertEqual(app.statistics(r)['failed_reviews'],1)
    def test_incompatible_version_and_missing_output_visible(self):
        self.batch(['A'],version='OLD_TEST_VERSION');self.batch(['B'],'2');d,r=self.cumulative();self.assertEqual(app.statistics(r)['failed_reviews'],1);self.assertTrue(any('不兼容' in row.get('error','') for row in r['results']))
    def test_same_text_different_original_ids_not_collapsed(self):
        d,_=self.batch(['A']);row=copy.deepcopy(d['reviews'][0]);row['raw']['review_id']='B';self.assertNotEqual(cumulative.identity(d,row)[0],cumulative.identity(d,d['reviews'][0])[0])
    def test_one_batch_and_other_product_do_not_create_fake_cumulative(self):
        self.batch(['A']);cumulative.refresh(app);self.assertFalse(any(app.load(p).get('derived_kind') for p in app.DATA.glob('dataset_*.json')));self.batch(['B'],'2',asin='OTHER_ASIN');cumulative.refresh(app);self.assertFalse(any(app.load(p).get('derived_kind') for p in app.DATA.glob('dataset_*.json')))
    def test_unchanged_inputs_reuse_snapshot_and_export_lineage(self):
        self.batch(['A']);self.batch(['B'],'2');d,r=self.cumulative();snapshot=app.run_path(r['id']).read_bytes();d2,r2=self.cumulative();self.assertEqual(r2['id'],r['id']);self.assertEqual(app.run_path(r['id']).read_bytes(),snapshot)
        report=app.thematic_summary(r)['report'];self.assertIn('累计分析报告',app.insights.markdown(report));self.assertIn('所属批次',app.insights.markdown(report));z=zipfile.ZipFile(io.BytesIO(app.export_zip(d,r)));self.assertIn('batch_lineage.json',z.namelist());self.assertIn('cumulative_reviews.csv',z.namelist());self.assertEqual(z.read('batch_brief.md').decode(),report['brief_markdown']);self.assertEqual(len(json.loads(z.read('raw_reviews.json'))['reviews']),2)
    def test_cumulative_cannot_start_remote_analysis(self):
        self.batch(['A']);self.batch(['B'],'2');d,r=self.cumulative()
        with self.assertRaisesRegex(ValueError,'原批次'):app.create_run(d,{})
