#!/usr/bin/env python3
"""Audit only the clean release directory; never print matching secret values."""
from pathlib import Path
import json,re,hashlib,sys,subprocess
ROOT=Path(__file__).resolve().parents[1]
issues=[];files=[]
for p in ROOT.rglob('*'):
    if not p.is_file() or any(x in p.parts for x in ['.git','__pycache__']):continue
    rel=p.relative_to(ROOT).as_posix();data=p.read_bytes();files.append({'path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    if p.suffix.lower() in ['.zip','.log','.db','.pem','.key','.sqlite'] or rel.startswith(('local_app/runs/','local_app/summaries/','local_app/curation/','local_app/benchmarks/','local_app/plans/')):issues.append(rel+': private artifact type/directory')
    if rel.startswith('local_app/data/') and p.name not in ['upload_template.csv','source_report.md']:issues.append(rel+': non-allowlisted local data')
    if p.name.startswith('.env') and p.name!='.env.example':issues.append(rel+': private configuration')
    if p.suffix.lower() in ['.jpg','.png','.jpeg']:continue
    text=data.decode('utf-8')
    patterns=[r'sk-[A-Za-z0-9_-]{20,}',r'gh[pousr]_[A-Za-z0-9]{20,}',r'github_pat_[A-Za-z0-9_]{20,}',r'-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----']
    if any(re.search(pattern,text) for pattern in patterns):issues.append(rel+': possible credential (value suppressed)')
    if rel.startswith('docs/') and re.search(r'https?://(?:localhost|127\.0\.0\.1|api\.codelink\.chat)',text):issues.append(rel+': local/service address in public artifact')
    if rel.startswith('docs/') and p.suffix=='.html' and re.search(r'(?:href|src)="/(?!echo-feedback-lab/)',text):issues.append(rel+': root-absolute resource path')
case=json.loads((ROOT/'demo_source/generated_case.json').read_text());public=json.loads((ROOT/'docs/assets/demo.json').read_text())
assert case['data_kind']==public['data_kind']=='synthetic_demo'
assert len(case['dataset']['reviews'])==len(public['dataset']['reviews'])==16
for review in public['dataset']['reviews']:
    assert review['raw']['data_kind']=='synthetic_demo' and review['raw']['source']=='项目自编模拟评论 · 非真实消费者'
for f in public['view']['aggregate']['report']['keeps']+public['view']['aggregate']['report']['issues']:
    assert f['count']==len({s['review_id'] for s in f['sources']}) and f['denominator']==16
for c in public['view']['aggregate']['categories']:
    for g in c['groups']:assert g['count']==len({s['review_id'] for s in g['sources']})
# Every public evidence quote must still point to its synthetic source field.
raw={r['id']:r['raw'] for r in public['dataset']['reviews']}
for c in public['view']['aggregate']['categories']:
    for g in c['groups']:
        for source in g['sources']:assert source['evidence'] in raw[source['review_id']][source['evidence_field']]
if issues:
    print(json.dumps({'status':'BLOCKED','issues':issues},ensure_ascii=False));sys.exit(1)
print(json.dumps({'status':'PASS','files':len(files),'synthetic_reviews':16,'evidence_and_counts':'PASS','secret_and_private_artifact_scan':'PASS','public_paths':'PASS'},ensure_ascii=False))
if '--manifest' in sys.argv:print(json.dumps(files,ensure_ascii=False,indent=2))
