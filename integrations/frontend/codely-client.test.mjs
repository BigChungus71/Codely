import test from 'node:test';
import assert from 'node:assert/strict';
import {createCodelyClient, CodelyApiError, toDisplayFinding, completedFindings} from './codely-client.ts';
const finding={id:'real-id',rule_id:'rule',source:'semgrep',severity:'HIGH',title:'Scanner title',message:'Original evidence',file:'backend/Example.java',start_line:12,end_line:14,cwe:[],evidence:{}};
test('maps backend fields to existing scanner display shape without inventing advice',()=>{
 assert.deepEqual(toDisplayFinding(finding),{id:'real-id',severity:'high',scannerSeverity:'HIGH',title:'Scanner title',description:'Original evidence',file:'backend/Example.java',line:12});
 assert.match(toDisplayFinding({...finding,severity:'UNKNOWN'}).description,/UNKNOWN/);
});
test('only a completed empty scan is displayed as clean',()=>{
 for(const status of ['stale','not_scanned']) assert.throws(()=>completedFindings({status,findings:[]}),/successful scan/);
 assert.deepEqual(completedFindings({status:'completed',findings:[]}),[]);
});
test('routes, methods, and encoded file paths match backend contracts',async()=>{
 const calls=[];
 const client=createCodelyClient('http://localhost:8000/',async(url,options)=>{calls.push([url,options.method]);return new Response(JSON.stringify({}),{status:200});});
 await client.projects();await client.tree('voice-ai-agent');await client.file('voice-ai-agent','backend/a b.java');await client.scan('voice-ai-agent');await client.findings('voice-ai-agent');await client.explain('voice-ai-agent','id/1');await client.architecture('voice-ai-agent');
 assert.deepEqual(calls,[['http://localhost:8000/api/projects','GET'],['http://localhost:8000/api/projects/voice-ai-agent/tree','GET'],['http://localhost:8000/api/projects/voice-ai-agent/files?path=backend%2Fa+b.java','GET'],['http://localhost:8000/api/projects/voice-ai-agent/scan','POST'],['http://localhost:8000/api/projects/voice-ai-agent/findings','GET'],['http://localhost:8000/api/projects/voice-ai-agent/findings/id%2F1/explain','POST'],['http://localhost:8000/api/projects/voice-ai-agent/architecture','GET']]);
});
test('unavailable service propagates instead of becoming fake findings',async()=>{
 const client=createCodelyClient('',async()=>new Response(JSON.stringify({detail:'Scanner unavailable'}),{status:503}));
 await assert.rejects(client.scan('voice-ai-agent'),e=>e instanceof CodelyApiError&&e.status===503&&e.message==='Scanner unavailable');
});
