from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from main import app
from codely import api, adapters

@pytest.fixture
def demo(tmp_path, monkeypatch):
    (tmp_path/'backend').mkdir()
    (tmp_path/'backend/Example.java').write_text('class Example {\n String password = "example";\n}\n')
    (tmp_path/'node_modules').mkdir()
    (tmp_path/'node_modules/ignored.ts').write_text('ignored')
    (tmp_path/'.env').write_text('SECRET=do-not-return')
    (tmp_path/'binary.ts').write_bytes(b'\0binary')
    (tmp_path/'huge.ts').write_text('x'*512001)
    monkeypatch.setenv('VOICE_AI_AGENT_PATH', str(tmp_path))
    for key in ['CODELY_SCANNER_ADAPTER','CODELY_ARCHITECTURE_ADAPTER','CODELY_EXPLANATION_ADAPTER','GEMINI_API_KEY','SEMGREP_CONFIG']:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('CODELY_PYTHON_DEMO_PATH', str(tmp_path / 'missing'))
    monkeypatch.delenv('CODELY_ALLOW_EXTERNAL_AI', raising=False)
    api.cache.clear()
    return TestClient(app), tmp_path


def finding():
    return {'id': 'test-finding', 'rule_id': 'test-rule', 'source': 'test-adapter', 'severity': 'HIGH', 'title': 'Test contract', 'file': 'backend/Example.java', 'start_line': 2, 'end_line': 2, 'message': 'Test evidence', 'cwe': []}


def test_startup_and_legacy_routes(demo):
    client, _ = demo
    assert client.get('/').status_code == 200
    schema = client.get('/openapi.json').json()
    assert '/index' in schema['paths'] and '/upload-doc' in schema['paths']
    assert '/api/projects/{project_id}/scan' in schema['paths']


def test_repository(demo):
    client, root = demo
    assert client.get('/api/projects').json()['projects'][0]['status'] == 'ready'
    response = client.get('/api/projects/voice-ai-agent/tree').json()
    assert response['tree'] == [{'name': 'backend', 'path': 'backend', 'type': 'directory', 'children': [{'name':'Example.java','path':'backend/Example.java','type':'file'}]}]
    assert 'class Example' in client.get('/api/projects/voice-ai-agent/files', params={'path':'backend/Example.java'}).json()['content']
    for path, status in [('../outside.java',403),('/etc/passwd',403),('.env',415),('binary.ts',415),('huge.ts',413),('missing.java',404),('node_modules/ignored.ts',415)]:
        assert client.get('/api/projects/voice-ai-agent/files', params={'path':path}).status_code == status
    (root/'link.java').symlink_to(root/'backend/Example.java')
    assert client.get('/api/projects/voice-ai-agent/files', params={'path':'link.java'}).status_code == 403
    assert client.get('/api/projects/unknown/tree').status_code == 404


def test_missing_repository(demo, monkeypatch):
    client, root = demo
    monkeypatch.setenv('VOICE_AI_AGENT_PATH', str(root/'missing'))
    assert client.get('/api/projects').status_code == 503


def test_unavailable_services(demo, monkeypatch):
    client, _ = demo
    monkeypatch.setattr(adapters.shutil,'which',lambda _: None)
    assert client.get('/api/projects/voice-ai-agent/findings').json()['status'] == 'not_scanned'
    assert client.post('/api/projects/voice-ai-agent/scan').status_code == 503
    assert client.get('/api/projects/voice-ai-agent/architecture').status_code == 503
    assert client.post('/api/projects/voice-ai-agent/findings/x/explain').status_code == 409


def test_scan_cache_and_staleness(demo, monkeypatch):
    client, root = demo
    calls=[]
    monkeypatch.setattr(adapters,'scan_repository',lambda path: calls.append(path) or {'findings':[finding()]})
    url='/api/projects/voice-ai-agent'
    first=client.post(url+'/scan').json()
    assert first['status']=='completed' and first['cached'] is False
    assert client.post(url+'/scan').json()['cached'] is True and len(calls)==1
    assert client.get(url+'/findings').json()['findings'][0]['id']=='test-finding'
    (root/'backend/Example.java').write_text('class Changed {\n String x;\n}\n')
    assert client.get(url+'/findings').json()['status']=='stale'
    assert client.post(url+'/findings/test-finding/explain').status_code==409
    assert client.post(url+'/scan').json()['cached'] is False and len(calls)==2


def test_empty_and_invalid_scan(demo, monkeypatch):
    client,_=demo
    url='/api/projects/voice-ai-agent/scan'
    monkeypatch.setattr(adapters,'scan_repository',lambda _: {'findings':[]})
    assert client.post(url).json()['findings']==[]
    api.cache.clear()
    monkeypatch.setattr(adapters,'scan_repository',lambda _: {'findings':[], 'errors':[{'message':'partial'}]})
    assert client.post(url).status_code==502 and not api.cache
    monkeypatch.setattr(adapters,'scan_repository',lambda _: {'findings':[{**finding(),'end_line':999}]})
    assert client.post(url).status_code==502


def test_explanation_and_graph_contracts(demo,monkeypatch):
    client,_=demo
    url='/api/projects/voice-ai-agent'
    monkeypatch.setattr(adapters,'scan_repository',lambda _: {'findings':[finding()]})
    client.post(url+'/scan')
    assert client.post(url+'/findings/test-finding/explain').status_code==503
    captured=[]
    def explain(f,ctx):
        captured.append(ctx)
        return {'finding_id':f['id'],'explanation':'Test-only explanation','potential_impact':'Test impact','recommendation':'Test advice'}
    monkeypatch.setattr(adapters,'explain',explain)
    assert client.post(url+'/findings/test-finding/explain').json()['requires_developer_review'] is True
    assert captured[0]['file']=='backend/Example.java'
    assert client.post(url+'/findings/missing/explain').status_code==404
    monkeypatch.setattr(adapters,'explain',lambda *_: {'finding_id':'wrong'})
    assert client.post(url+'/findings/test-finding/explain').status_code==502
    monkeypatch.setattr(adapters,'architecture',lambda _: {'nodes':[{'id':'x','label':'Example','type':'class','file':'backend/Example.java'}], 'edges':[]})
    assert client.get(url+'/architecture').status_code==200
    monkeypatch.setattr(adapters,'architecture',lambda _: {'nodes':[], 'edges':[{'source':'x','target':'y','relationship':'dependency'}]})
    assert client.get(url+'/architecture').status_code==502


def test_scan_change_during_run(demo,monkeypatch):
    client,root=demo
    def scanner(_):
        (root/'changed.txt').write_text('changed during scan')
        return {'findings':[]}
    monkeypatch.setattr(adapters,'scan_repository',scanner)
    assert client.post('/api/projects/voice-ai-agent/scan').status_code==409
    assert not api.cache


def test_semgrep_normalization(demo, monkeypatch):
    import json, subprocess
    _, root=demo
    monkeypatch.setenv('SEMGREP_CONFIG','local-rules.yml')
    monkeypatch.setattr(adapters.shutil,'which',lambda _: '/test/semgrep')
    raw={'check_id':'rule', 'path':'backend/Example.java','start':{'line':2},'end':{'line':2},'extra':{'severity':'ERROR','message':'Evidence','metadata':{'cwe':['CWE-798']}}}
    monkeypatch.setattr(adapters.subprocess,'run',lambda *a,**kw: subprocess.CompletedProcess(a,0,json.dumps({'results':[raw],'errors':[]})))
    result=adapters.scan_repository(str(root))
    assert result['findings'][0]['severity']=='HIGH'
    assert result['findings'][0]['evidence']==raw


def test_scan_timeout(demo,monkeypatch):
    _,root=demo
    monkeypatch.setenv('SEMGREP_CONFIG','local-rules.yml')
    monkeypatch.setattr(adapters.shutil,'which',lambda _: '/test/semgrep')
    def run(*args,**kwargs): raise adapters.subprocess.TimeoutExpired('semgrep',90)
    monkeypatch.setattr(adapters.subprocess,'run',run)
    with pytest.raises(HTTPException) as error: adapters.scan_repository(str(root))
    assert error.value.status_code==504


def test_scan_lock(demo):
    client,_=demo
    api.scan_lock.acquire()
    try:
        assert client.post('/api/projects/voice-ai-agent/scan').status_code==409
    finally:
        api.scan_lock.release()


def test_frontend_cross_origin(demo):
    client, _ = demo
    response = client.options('/api/projects/voice-ai-agent/scan', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == '*'


def test_design_question_uses_doc_evidence_and_constraints(demo, monkeypatch):
    from codely import teammate_services

    client, root = demo
    (root / 'DESIGN.md').write_text('Capacity planning considers concurrency and a limited infrastructure budget.\n')

    class Provider:
        def generate(self, instruction, payload, schema):
            assert payload['constraints'] == 'Limited infrastructure budget'
            evidence = next(entry for entry in payload['evidence'] if entry['path'] == 'DESIGN.md')
            return schema(answer='Assess capacity before scaling.', cited_evidence=[evidence['id']])

    monkeypatch.setattr(teammate_services, 'live_provider', Provider)
    response = client.post('/api/projects/voice-ai-agent/design-question', json={
        'question': 'How do we plan capacity and concurrency?',
        'constraints': 'Limited infrastructure budget',
    })
    assert response.status_code == 200
    assert response.json()['sources'][0]['file'] == 'DESIGN.md'
