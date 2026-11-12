'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(process.argv[2],'utf8');
function browser(){
 const calls=[],redirects=[],intervals=new Map(),timeouts=new Map(),listeners={},events=[];
 let response=()=>new Response(JSON.stringify({user:null}),{status:200}),nextTimer=0,paused=0;
 const document={hidden:false,querySelectorAll:()=>[{pause(){paused++;}},{pause(){paused++;}}],addEventListener(name,handler){listeners[name]=handler;}};
 const window={location:{href:'https://electronicama.test/',origin:'https://electronicama.test',replace:url=>redirects.push(url)},
  fetch:async(...args)=>{calls.push(args);return response(...args);},dispatchEvent:event=>events.push(event.type),addEventListener(name,handler){listeners[name]=handler;},
  setInterval:fn=>{intervals.set(++nextTimer,fn);return nextTimer;},clearInterval:id=>intervals.delete(id),setTimeout:fn=>{timeouts.set(++nextTimer,fn);return nextTimer;},clearTimeout:id=>timeouts.delete(id)};
 vm.runInNewContext(source,{window,document,URL,AbortController,CustomEvent:class{constructor(type){this.type=type;}}});
 return {window,document,calls,redirects,intervals,timeouts,listeners,events,setResponse:fn=>{response=fn;},paused:()=>paused};
}
(async()=>{
 const anonymous=browser(),options={method:'POST',body:'data',headers:{'X-Test':'value'}};
 const original=new Response('{"user":null}',{status:200});
 anonymous.setResponse(()=>original);
 const result=await anonymous.window.fetch('/api/account/me',options);
 assert.equal(result,original,'wrapping must preserve the response');
 assert.equal(anonymous.calls[0][1],options,'fetch options must be passed unchanged');
 assert.equal((await result.json()).user,null,'inspecting must not consume the caller body');
 assert.equal(anonymous.intervals.size,0,'anonymous visitors must not poll');

 const member=browser();member.setResponse(()=>new Response('{"user":{"id":"member-id"}}'));
 await member.window.fetch('/api/account/me');
 assert.equal(member.intervals.size,1);
 await member.window.fetch('/api/account/me');assert.equal(member.intervals.size,1,'only one interval');
 const tick=[...member.intervals.values()][0];
 member.document.hidden=true;await tick();assert.equal(member.calls.length,2,'hidden pages must not make requests');
 member.document.hidden=false;await tick();assert.equal(member.calls.length,3);
 assert.equal(member.calls[2][1].cache,'no-store');assert.equal(member.timeouts.size,0);
 member.setResponse(()=>{throw new Error('offline');});await tick();
 assert.equal(member.redirects.length,0,'offline is not an account block');
 assert.equal(member.timeouts.size,0,'poll timeouts must be cleaned up');
 member.setResponse(()=>new Response('{"user":null}'));await tick();assert.equal(member.intervals.size,0,'logout stops polling');

 const blocked=browser();blocked.setResponse(()=>new Response('{"user":{"id":"member-id"}}'));
 await blocked.window.fetch('/api/account/me');
 blocked.setResponse(()=>new Response('{"code":"csrf_expired"}',{status:403}));await blocked.window.fetch('/api/write');
 blocked.setResponse(()=>new Response('not json',{status:403}));await blocked.window.fetch('/api/other');
 blocked.setResponse(()=>new Response('{"code":"account_blocked"}',{status:401}));await blocked.window.fetch('/api/login');
 blocked.setResponse(()=>new Response('{"code":"account_blocked"}',{status:403}));
 await blocked.window.fetch('https://elsewhere.test/api');assert.equal(blocked.redirects.length,0,'third-party responses cannot block this account');
 const request={url:'https://electronicama.test/api/music'};
 const denied=await blocked.window.fetch(request);
 assert.equal((await denied.json()).code,'account_blocked');
 assert.deepEqual(blocked.redirects,['/account?blocked=1']);
 assert.equal(blocked.paused(),2,'all local playback must pause');
 assert.deepEqual(blocked.events,['electronicama:account-blocked']);assert.equal(blocked.intervals.size,0);
 await blocked.window.fetch('/api/account/me');assert.equal(blocked.redirects.length,1,'parallel denials must not create redirect loops');
 console.log('OK: blocked account exits, preserved fetch responses, authenticated polling, hidden/logout/offline handling and unrelated denials');
})().catch(error=>{console.error(error);process.exitCode=1;});
