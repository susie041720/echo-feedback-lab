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
