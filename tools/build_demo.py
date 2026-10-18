#!/usr/bin/env python3
"""Build static, synthetic-only Pages demo from saved real model extractions.
Never calls a model or reads local research stores. Python standard library only.
"""
import argparse,copy,json,re,sys,tempfile,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'local_app'))
import app

def replace_function(source,name,replacement):
    start=re.search(r'(?m)^(?:async )?function '+re.escape(name)+r'\(',source)
    if not start:raise ValueError('Shared UI function missing: '+name)
    next_fn=re.search(r'(?m)^(?:async )?function ',source[start.end():])
    end=start.end()+next_fn.start() if next_fn else len(source)
    return source[:start.start()]+replacement+'\n'+source[end:]

def build():
    case=json.loads((ROOT/'demo_source/generated_case.json').read_text())
    assert case['data_kind']=='synthetic_demo' and case['dataset']['provenance']['not_real_consumers'] is True
    d=case['dataset'];run=case['run']
    assert len(d['reviews'])==16 and all(r['raw'].get('data_kind')=='synthetic_demo' for r in d['reviews'])
    for row in d['reviews']:
        assert row['raw']['source']=='项目自编模拟评论 · 非真实消费者'
        assert row['raw']['title'].startswith('[模拟] ')
        assert not row['raw'].get('user_id') and not row['raw'].get('source_url')
    for result in run['results']:
        raw=next(x['raw'] for x in d['reviews'] if x['id']==result['review_id'])
        if result['status']=='completed':
            check=copy.deepcopy(result['analysis'])
            for a in check['aspects']:a.pop('id',None)
            app.check_analysis(check,raw)
    with tempfile.TemporaryDirectory() as directory:
        app.DATA=Path(directory)/'data';app.RUNS=Path(directory)/'runs';app.SUMMARIES=Path(directory)/'summaries';app.ROOT=Path(directory)
        app.save(app.dataset_path(d['id']),d);app.save(app.run_path(run['id']),run)
        view=app.run_view(copy.deepcopy(run));full_findings=app.thematic_summary(copy.deepcopy(run))['report']['findings']
    report=view['aggregate']['report']
    report['title']='模拟评论演示报告'
    report['limitations'].insert(0,'本案例16条评论为项目自编模拟数据，产品回声 AF4 为虚构型号。用于功能演示，不能作为真实消费者研究、市场比例或准确率证据。')
    for key in ['service_base','usage','usage_lineage','historical_timings','performance','quality_gate']:report.pop(key,None)
    report['brief_markdown']=app.insights.markdown(report,include_evidence=False)
    view['usage']={};view['run']={k:run[k] for k in ['id','dataset_id','product','created_at','status','model','prompt_version','review_ids','results','human_reviews']}
    view['run']['results']=[{'review_id':x['review_id'],'status':x['status']} for x in run['results']]
    payload={'data_kind':'synthetic_demo','dataset':d,'view':view,'taxonomy':app.thematic.CONFIG,'generation':case['generation']}
    docs=ROOT/'docs';(docs/'assets').mkdir(exist_ok=True);(docs/'reports').mkdir(exist_ok=True)
    (docs/'assets/demo.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')))
    (docs/'reports/demo-report.md').write_text(report['brief_markdown'])
    full_report=copy.deepcopy(report);full_report['findings']=full_findings
    (docs/'reports/demo-full-report.md').write_text(app.insights.markdown(full_report,include_evidence=True))
    (docs/'.nojekyll').write_text('')
    source=(ROOT/'local_app/static/app.js').read_text();source=source[:source.index('function renderQuality(')]
    source=replace_function(source,'api',"""let demoPayload=null;
async function api(path,body){if(body)throw Error('公开演示使用预置结果；真实分析及修订请使用本地完整版。');if(!demoPayload){const response=await fetch('./assets/demo.json');if(!response.ok)throw Error('示例文件加载失败，请刷新重试。');demoPayload=await response.json();if(demoPayload.data_kind!=='synthetic_demo')throw Error('演示数据类型校验失败。')}const p=demoPayload;if(path.startsWith('/api/state'))return {datasets:[{id:p.dataset.id,product:p.dataset.product,count:p.dataset.reviews.length,created_at:p.dataset.created_at}],runs:[p.view.run],app_version:'5.0-demo-case',taxonomy:p.taxonomy,env_key_available:false};if(path.startsWith('/api/dataset'))return p.dataset;if(path.startsWith('/api/selection'))return {review_ids:[],items:[]};if(path.startsWith('/api/run'))return p.view;throw Error('此功能仅在本地完整版中提供。')}
""")
    source=replace_function(source,'refreshState',"""async function refreshState(){state=await api('/api/state');const chosen=dataset?.id||$('dataset').value;$('dataset').replaceChildren();option($('dataset'),'','选择示例批次');for(const d of state.datasets)option($('dataset'),d.id,`${d.product} · ${d.count} 条`);$('dataset').value=chosen;fillRuns()}""")
    source=replace_function(source,'classifier',"function classifier(){return el('span')}")
    source=replace_function(source,'openSettings',"function openSettings(){notice('公开演示只读取模拟评论的预置结果；上传、实时分析和可选修订请使用 GitHub 中的本地完整版。')}")
    source=replace_function(source,'setPage',"""function setPage(){if(location.hash==='#main-content')return;window.scrollTo(0,0);const path=location.hash.replace(/^#\\/?/,'').split('?')[0],params=new URLSearchParams(location.hash.split('?')[1]||'');page='analysis';tab=path==='themes'?'themes':path==='report'?'report':path==='evidence'?(['raw','feedback','scenarios'].includes(params.get('view'))?params.get('view'):'raw'):['summary','themes','report','raw','feedback','scenarios'].includes(params.get('tab'))?params.get('tab'):'summary';render()}
""")
    source=replace_function(source,'scopeNote',"function scopeNote(root){root.append(el('p',`当前展示 ${current.statistics.completed_reviews} 条模拟评论的预置分析；数量仅描述此演示样本。`,'sample-scope'))}")
    source=source.replace("if(page==='debug'){renderDebug(root);return}if(page==='batch'){renderBatch(root);return}if(page==='quality'){renderQuality(root);return}",'')
    source=source.replace("'/api/report?run='+current.run.id+'&brief=1'","'./reports/demo-report.md'").replace("'/api/report?run='+current.run.id","'./reports/demo-full-report.md'")
    source=re.sub(r"\$\('export'\)\.href=dataset\?.*?:'#';", "$('export').href='./reports/demo-report.md';$('export').download='echo-simulated-demo-report.md';$('export').textContent='导出演示报告 ↓';",source)
    source=source.replace("completed:'分析完成'", "completed:'示例已加载'")
    source=source.replace("$('current-product').textContent=", "for(const id of ['dataset','run']){const placeholder=$(id).options[0];if(placeholder){placeholder.disabled=true;placeholder.hidden=true}}$('current-product').textContent=")
    source=source.replace("${localTime(r.created_at)} · ${status}","预置示例 · ${status}")
    source=re.sub(r"c.append\(el\('p',`评论记录：\$\{row.id\}`,'meta'\),link\('开发调试中查看完整原始字段'.*?\$\('evidence'\)\.showModal\(\);", "c.append(el('p',`模拟评论记录：${row.raw.review_id}`,'meta'));$('evidence').showModal();",source)
    source=source.replace("if(current.run.status!=='running'&&current.run.workflow&&report.success<report.raw_count)root.append(button('重试失败／未完成记录（同版本成功项复用）',()=>{$('sample').value='daily';$('analyze').click()}))",'')
    source=source.replace('导入消费者评论','读取模拟示例').replace('上传有权使用的 CSV，分析后直接查看结果。','正在读取预置示例；加载失败时请刷新重试。')
    source+='''
$('dataset').addEventListener('change',()=>selectDataset($('dataset').value).catch(e=>notice(e.message,true)));
$('run').addEventListener('change',()=>{if($('run').value)loadRun($('run').value);else{++loadVersion;clearTimeout(timer);current=null;render()}});
for(const n of document.querySelectorAll('[data-tab]'))n.addEventListener('click',()=>activateTab(n.dataset.tab));
for(const id of ['category','topic','polarity','scope'])$(id).addEventListener('change',render);
$('close-dialog').addEventListener('click',()=>$('evidence').close());$('close-theme').addEventListener('click',()=>$('theme-detail').close());
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('close',()=>{if(!document.querySelector('dialog[open]'))render()});
window.addEventListener('hashchange',setPage);
refreshState().then(async()=>{await selectDataset(state.datasets[0].id);setPage()}).catch(e=>notice(e.message,true));
'''
    (docs/'app.js').write_text(source)
    html=(ROOT/'local_app/static/index.html').read_text().replace('href="/style.css"','href="./style.css"').replace('src="/app.js"','src="./app.js"')
    html=html.replace('<title>回声 · 消费者反馈分析工作台</title>','<title>回声 · 消费者反馈分析｜模拟数据演示</title><meta name="description" content="面向产品和运营人员的消费者反馈分析作品原型。使用明确标注的模拟评论，展示核心发现、主题、不同评价、行动建议和原文追溯。">')
    start=html.index(' <div class="sidebar-bottom">');end=html.index('\n</aside>',start)
    html=html[:start]+''' <div class="sidebar-bottom"><p class="nav-caption">关于项目</p><nav class="utility-nav"><a href="https://github.com/susie041720/echo-feedback-lab" target="_blank" rel="noopener">↗ 项目代码与说明</a><a href="https://github.com/susie041720/echo-feedback-lab#本地启动" target="_blank" rel="noopener">↗ 本地完整版使用</a></nav><div class="local"><i></i>模拟数据 · 静态演示</div></div>'''+html[end:]
    html=re.sub(r'<button[^>]*data-settings="[^"]+"[^>]*>.*?</button>','',html)
    html=html.replace('<button id="analyze" class="primary" disabled>开始分析</button>','<a class="primary demo-button" href="#/analysis">查看示例分析</a><button id="analyze" hidden disabled></button>')
    html=html.replace('download="feedback_export.zip"','download="echo-simulated-demo-report.md"').replace('导出结果 ↓','导出演示报告 ↓')
    marker='<section class="metrics"'
    html=html.replace(marker,'''<aside class="demo-banner" aria-label="演示范围"><strong>模拟评论演示 · 预置分析结果</strong><p>回声帮助产品和运营从评论中归纳重点、追溯证据并制定调查方向。本例使用16条自编模拟评论及虚构型号，结果由真实模型流程生成；浏览时不调用模型，不代表真实消费者研究。</p></aside>\n  '''+marker,1)
    start=html.index('<dialog id="settings"');end=html.index('<dialog id="theme-detail"',start)
    html=html[:start]+'''<div hidden><input id="product"><input id="key" type="password" disabled><select id="sample"><option value="daily">daily</option></select><p id="sample-info"></p><p id="source-status"></p><p id="source-description"></p><p id="import-info"></p><button id="developer-trial"></button></div><dialog id="settings" hidden><p id="settings-notice"></p></dialog>\n'''+html[end:]
    html=html.replace('原始评论</div>','模拟评论</div>').replace('明确负面实际体验','明确负面体验描述')
    html=html.replace('AI 归纳可能有误判，未确定信息保持原状。满意度和复购率尚未验证。','作品原型 · 本例为模拟数据，AI 归纳仍可能误判。未验证实际效率、满意度或复购效果。')
    (docs/'index.html').write_text(html)
    css=(ROOT/'local_app/static/style.css').read_text()+'''\n.demo-banner{padding:12px 16px;background:#eef3f9;border:1px solid #d7e1ed;border-radius:7px;margin-bottom:16px;color:#344e67}.demo-banner strong{font-size:13px}.demo-banner p{font-size:12px;margin:4px 0 0}.demo-button{display:inline-flex;align-items:center;min-height:36px;padding:7px 12px;background:#237653;border-radius:6px;color:white;font-size:13px;font-weight:600}.demo-button:hover{background:#195c40;text-decoration:none}.toolbar-actions .export{font-size:12px} .toolbar{grid-template-columns:minmax(155px,1fr) minmax(330px,2.25fr) auto}@media(max-width:1180px){.toolbar{grid-template-columns:minmax(140px,1fr) auto}}@media(max-width:760px){.demo-banner{padding:11px 12px}.demo-button{font-size:12px;padding:7px 9px}.demo-banner p{font-size:12px}}
'''
    (docs/'style.css').write_text(css)
    # Friendly static fallback; all supported subviews use hashes and refresh normally.
    (docs/'404.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>回声 · 返回演示</title><body style="font-family:sans-serif;padding:3rem"><h1>回声消费者反馈分析</h1><p>此地址不存在。分析概览、主题、报告和证据使用页面内导航。</p><a href="/echo-feedback-lab/#/analysis">返回公开演示</a></body></html>')
    print(json.dumps({'built':'docs','reviews':len(d['reviews']),'successful':view['statistics']['completed_reviews'],'core_keeps':len(report['keeps']),'core_issues':len(report['issues']),'difference_themes':[(c['name'],c.get('conflict_theme_keys')) for c in view['aggregate']['categories'] if c.get('conflict_theme_keys')]},ensure_ascii=False))
if __name__=='__main__':build()
