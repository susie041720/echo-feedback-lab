"""Conservative evidence attributes. No reviewer profile or unmentioned cause inference."""
import re

VERSION='comparison-context-3-explicit-chinese'

def comparison(source,raw=None):
    quote=source.get('evidence','');basis='未知';reference='未说明比较对象';match=None
    context=quote;text=(raw or {}).get(source.get('evidence_field'),'')
    if quote and text.count(quote)==1:
        start=text.index(quote);end=start+len(quote)
        left=max(text.rfind(mark,0,start) for mark in '.!?。！？\n')+1
        endings=[text.find(mark,end) for mark in '.!?。！？\n'];right=end if quote[-1] in '.!?。！？\n' else min([n for n in endings if n>=0]+[len(text)-1])+1
        candidate=text[left:right].strip()
        if len(candidate)<1500:context=candidate
    patterns=[('相对于预期',r'\b(?:as I (?:thought|expected)[^.!?]*|than (?:I )?expected[^.!?]*|better than expected[^.!?]*)'),
              ('旧产品或其他产品',r'\b(?:compar(?:ed|ing) to|than (?:my |the |our )?(?:old|previous|oven|microwave)|instead of|in the (?:oven|microwave)|time it takes my oven)\b[^.!?]*'),
              ('相对于预期',r'比(?:购买前|买前)?(?:我|我们|我的)?(?:原先|原来)?(?:的)?(?:预期|想象|预想)[^。！？]*'),
              ('旧产品或其他产品',r'(?:相比|比)(?:我|我们|我的)?(?:以往|以前)?(?:用)?(?:的)?(?:旧款|旧机器|旧产品|烤箱|微波炉)[^。！？]*')]
    for label,pattern in patterns:
        found=re.search(pattern,context,re.I)
        if found:
            basis=label;reference=found.group().strip();match=reference;break
    if basis=='未知' and source.get('subject')=='本产品' and source.get('experience')=='实际经历':basis='实际体验的直接判断'
    return {'basis':basis,'reference':reference,'evidence':match,'evidence_field':source.get('evidence_field'),'context_evidence':context if context!=quote else None,'expectation_timing':'购买前' if re.search(r'before (?:buying|purchas)|购买前|买前',context,re.I) else '未知','rule_version':VERSION,'limit':'只读取该观点引文及唯一定位的同一句原文；未明说的比较对象、差异原因与画像保持未知。'}

def enrich(agg,raw_reviews=None):
    raw_reviews=raw_reviews or {}
    for category in agg['categories']:
        for group in category['groups']:
            for source in group['sources']:source['comparison']=comparison(source,raw_reviews.get(source['review_id']))
    for key in ['scenarios','behaviors','overall_evaluations']:
        for source in agg.get(key,[]):source['comparison']=comparison(source,raw_reviews.get(source['review_id']))
    return agg


def behavior_links(sources,behaviors,raw_reviews):
    ids={source['review_id'] for source in sources};links=[]
    for behavior in behaviors:
        if behavior['review_id'] not in ids or behavior.get('subject')!='本产品':continue
        item=dict(behavior);text=raw_reviews.get(behavior['review_id'],{}).get('text','')
        # Co-occurrence is not causality. Only an explicit return-because clause gives a reason link.
        cause=re.search(r'\bI returned because\b[^.!?]*[.!?]?',text,re.I)
        related=[s for s in sources if s['review_id']==behavior['review_id']]
        explicit=bool(cause and any(s.get('evidence') and s['evidence'].split('.')[0].strip('!? ') in cause.group() for s in related))
        item['association']='原文明示退货原因' if explicit else '同条评论另有行为或意向，未确认因果关联'
        item['association_evidence']=cause.group() if explicit else None
        item['actual_return']=behavior.get('experience')=='实际经历' and ('退货' in behavior.get('kind','') or '退货' in behavior.get('status',''))
        item['concerning_intent']=any(word in behavior.get('kind','')+behavior.get('claim','') for word in ['不推荐','不再购买','不再买','停止使用','停用'])
        links.append(item)
    return links


def safety_concern(sources):
    return [s for s in sources if s.get('subject')=='本产品' and s.get('bucket') in ['concern','unknown'] and re.search(r'\b(fire|accident|dangerous|injur\w*)\b',s.get('evidence',''),re.I)]
