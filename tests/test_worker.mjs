import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker.mjs';

test('relay auth, validation, ingest, read and stale detection', async () => {
  let stored;
  const env = {READ_KEY:'read-test',WRITE_KEY:'write-test',CAT_STATS:{
    get:async()=>stored, put:async(k,v)=>{stored=JSON.parse(v);}
  }};
  const send = (path,method='GET',key='',body) => worker.fetch(new Request('https://example.com'+path,{
    method, headers:{'x-api-key':key},body:body === undefined ? undefined : JSON.stringify(body)
  }),env);
  assert.equal((await send('/status')).status,401);
  assert.equal((await send('/status','GET','write-test')).status,401);
  assert.equal((await send('/status','GET','read-test')).status,503);
  assert.equal((await send('/ingest','POST','write-test',{})).status,400);
  const snapshot={schema_version:1,generated_at:Math.floor(Date.now()/1000),devices:[],pets:[],alerts:[]};
  assert.equal((await send('/ingest','POST','read-test',snapshot)).status,401);
  assert.equal((await send('/ingest','POST','write-test',snapshot)).status,200);
  assert.equal((await (await send('/status','GET','read-test')).json()).stale,false);
  stored.generated_at -= 901;
  assert.equal((await (await send('/status','GET','read-test')).json()).stale,true);
  assert.equal((await send('/ingest','POST','write-test','x'.repeat(70000))).status,413);
});
