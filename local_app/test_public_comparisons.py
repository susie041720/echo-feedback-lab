"""Synthetic development examples for explicit comparison boundaries."""
import unittest
import evidence
class ExplicitComparisonTests(unittest.TestCase):
    def classify(self,quote,text=None):return evidence.comparison({'evidence':quote,'evidence_field':'text','subject':'本产品','experience':'实际经历'},{'text':text or quote})
    def test_chinese_expectation(self):
        q='实际声音比我预想的小';r=self.classify(q,'购买前我觉得会很响，'+q+'。');self.assertEqual(r['basis'],'相对于预期');self.assertEqual(r['expectation_timing'],'购买前')
    def test_expectation_time_not_inferred(self):self.assertEqual(self.classify('清洗比我预想的省事')['expectation_timing'],'未知')
    def test_old_oven_explicit(self):self.assertEqual(self.classify('完成得比我以往用烤箱快')['basis'],'旧产品或其他产品')
    def test_direct_and_unknown_not_invented(self):
        r=self.classify('运行时声音偏大');self.assertEqual(r['basis'],'实际体验的直接判断');self.assertEqual(r['reference'],'未说明比较对象')
if __name__=='__main__':unittest.main()

class AliasAggregationTests(unittest.TestCase):
    def test_alias_preserves_sources_and_comparable_counts(self):
        import thematic
        def a(i,p):return {'id':'a'+i,'major_category':'environment','theme_key':'running-noise','feedback_kind':'产品反馈','topic':'TEST ONLY 运行噪音','polarity':p,'claim':'TEST ONLY 明确观点','evidence':'TEST ONLY','evidence_field':'text','subject':'本产品','experience':'实际经历','scenario':'未说明'}
        results=[{'review_id':i,'status':'completed','analysis':{'aspects':[a(i,p)],'uncertainties':[]}} for i,p in [('1','优点'),('2','槽点')]]
        agg=thematic.aggregate({'id':'TEST_ONLY','prompt_version':'2.0','results':results},results);cat=agg['categories'][0]
        self.assertEqual(cat['count'],2);self.assertEqual(cat['conflict_theme_keys'],['operating-noise']);self.assertEqual(cat['positive_count'],1);self.assertEqual(cat['negative_count'],1)
        self.assertEqual({s['aspect_id'] for g in cat['groups'] for s in g['sources']},{'a1','a2'})

class QuoteWhitespaceTests(unittest.TestCase):
    def test_unique_original_span_restored(self):
        import app
        value={'aspects':[{'evidence':'TEST ONLY word gap','evidence_field':'text','confidence':'高'}]}
        result,changes=app.normalize_analysis(value,{'text':'TEST ONLY word  gap.'})
        self.assertEqual(result['aspects'][0]['evidence'],'TEST ONLY word  gap');self.assertEqual(changes[-1]['rule'],'unique_whitespace_only_alignment_to_original_source')
    def test_ambiguous_or_changed_words_not_rewritten(self):
        import app
        value={'aspects':[{'evidence':'TEST ONLY word gap','evidence_field':'text','confidence':'高'}]}
        result,changes=app.normalize_analysis(value,{'text':'TEST ONLY word  gap and TEST ONLY word\tgap'})
        self.assertEqual(result['aspects'][0]['evidence'],'TEST ONLY word gap');self.assertFalse(changes)
        result,changes=app.normalize_analysis(value,{'text':'TEST ONLY different gap'})
        self.assertEqual(result['aspects'][0]['evidence'],'TEST ONLY word gap');self.assertFalse(changes)

class CanonicalTopicTests(unittest.TestCase):
    def aspect(self,**changes):
        a=dict(id='TEST_ONLY',major_category='other',theme_key='cooking-fit',feedback_kind='产品反馈',topic='烹饪方式适配',polarity='槽点',claim='TEST ONLY fit unclear',evidence='TEST ONLY',evidence_field='text',subject='本产品',experience='实际经历',scenario='未说明');a.update(changes);return a
    def test_fit_and_range_are_distinct_without_changing_information(self):
        import thematic
        for change,title in [({},'需求适配'),({'topic':'烹饪用途广泛','experience':'无法判断','polarity':'优点'},'用途范围'),({'feedback_kind':'用途描述','polarity':'中立'},'用途范围')]:
            a=self.aspect(**change);n=thematic.normalize_topic(a);self.assertEqual(n['topic'],title)
            for k in ['evidence','polarity','experience','feedback_kind','claim']:self.assertEqual(n[k],a[k])
            self.assertEqual(a['theme_key'],'cooking-fit');self.assertEqual(thematic.normalize_topic(n),n)
    def test_purchase_intent_is_not_folded_into_usage(self):
        import thematic
        a=self.aspect(feedback_kind='行为或意向',theme_key='future-cooking-use',topic='烹饪用途广泛',experience='用户期望');self.assertEqual(thematic.normalize_topic(a),a)
    def test_overall_aliases_preserve_actual_expectation_and_polarity(self):
        import thematic
        for topic,experience,polarity in [('整体感受','实际经历','优点'),('整体满意度','实际经历','槽点'),('整体使用评价','用户期望','中立')]:
            a=self.aspect(topic=topic,feedback_kind='整体评价',experience=experience,polarity=polarity);n=thematic.normalize_topic(a);self.assertEqual(n['topic'],'整体评价');self.assertEqual((n['polarity'],n['experience']),(polarity,experience))
        a=self.aspect(topic='整体涂层表现');self.assertEqual(thematic.normalize_topic(a)['topic'],'需求适配')
    def test_split_recounts_review_ids_without_polarity_cancellation(self):
        import thematic,copy
        fit=self.aspect(id='fit');scope=self.aspect(id='range',topic='烹饪用途广泛',polarity='中立',feedback_kind='用途描述');duplicate=copy.deepcopy(scope);duplicate['id']='range2'
        rows=[dict(review_id='TEST_R1',status='completed',analysis={'aspects':[fit,scope,duplicate]})]
        a=thematic.aggregate(dict(id='TEST_ONLY',prompt_version='2.0',results=rows),rows);groups=[g for c in a['categories'] for g in c['groups']];self.assertEqual(a['analyzed_count'],1);self.assertEqual({g['summary'] for g in groups},{'需求适配','用途范围'});self.assertTrue(all(g['count']==1 for g in groups));self.assertEqual(sum(c['negative_count'] for c in a['categories']),1);self.assertEqual(sum(c['positive_count'] for c in a['categories']),0)
    def test_unrelated_similar_names_not_merged(self):
        import thematic
        a=self.aspect(topic='整体涂层表现',theme_key='coating-quality');self.assertEqual(thematic.normalize_topic(a)['topic'],'整体涂层表现')
    def test_cleaning_label_and_core_title_are_concise(self):
        import thematic,insights
        a=self.aspect(topic='清理方便',theme_key='clean-ease',major_category='cleaning',polarity='优点');rows=[dict(review_id='TEST_R',status='completed',analysis={'aspects':[a]})];run=dict(id='TEST_ONLY',prompt_version='2.0',results=rows,review_ids=['TEST_R'],model='TEST_ONLY');agg=thematic.aggregate(run,rows);report=insights.build(agg,run,1);self.assertEqual(agg['categories'][0]['groups'][0]['summary'],'清洁方便');self.assertEqual(report['keeps'][0]['title'],'清洁方便');self.assertEqual(report['keeps'][0]['support_label'],'个别反馈')
