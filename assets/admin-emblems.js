/* Refresh public image assets without reloading the page or touching drafts. */
const TIMEOUT_MS=8000;
// The page baseline never advances to /health: old JavaScript may create new
// image nodes after a deployment, so their URLs still need the active revision.
let pageVersion=null,assetRevision=null,inFlight=null,forcePending=false,batch=0;
const failures=new Map(),lazyLoads=new WeakMap();

function assetURL(source){
 try{
  const url=new URL(source,document.baseURI);
  return url.origin===location.origin&&!url.username&&!url.password&&url.pathname.startsWith('/assets/')?url:null;
 }catch{return null;}
}
function current(record){return record.node.isConnected&&record.node.getAttribute(record.attribute)===record.original;}
function pruneFailures(version){for(const [node,record] of failures)if(!node.isConnected||node.getAttribute(record.attribute)!==record.original||record.version!==version)failures.delete(node);}

async function deploymentVersion(){
 const controller=new AbortController();let timer;
 try{
  return await Promise.race([
   (async()=>{
    const response=await fetch('/health',{cache:'no-store',signal:controller.signal});
    if(!response.ok)throw new Error('No se pudo comprobar la versión de los emblemas.');
    const data=await response.json();
    if(typeof data.version!=='string'||!/^[A-Za-z0-9._-]{1,80}$/.test(data.version))throw new Error('La versión de los emblemas no es válida.');
    return data.version;
   })(),
   new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new Error('La actualización de emblemas tarda demasiado.'));},TIMEOUT_MS);})
  ]);
 }finally{clearTimeout(timer);}
}

function preload(source){
 return new Promise((resolve,reject)=>{
  const image=new Image();let finished=false;
  const finish=error=>{
   if(finished)return;finished=true;clearTimeout(timer);image.onload=image.onerror=null;
   if(error){image.src='';reject(error);}else resolve();
  };
  const timer=setTimeout(()=>finish(new Error('La imagen tarda demasiado.')),TIMEOUT_MS);
  image.onload=async()=>{try{if(image.decode)await image.decode();finish();}catch{finish(new Error('No se pudo leer la imagen.'));}};
  image.onerror=()=>finish(new Error('No se pudo actualizar la imagen.'));
  image.src=source;
 });
}

function deferLazy(record,source,version){
 const node=record.node,previous=lazyLoads.get(node),fallback=previous?.fallback??record.original;
 previous?.cleanup();
 const cleanup=()=>{node.removeEventListener('load',loaded);node.removeEventListener('error',failed);lazyLoads.delete(node);};
 const loaded=()=>{cleanup();};
 const failed=()=>{
  cleanup();
  if(!node.isConnected||node.getAttribute('src')!==source)return;
  node.setAttribute('src',fallback);failures.set(node,{attribute:'src',original:fallback,version});
 };
 lazyLoads.set(node,{fallback,cleanup});node.addEventListener('load',loaded,{once:true});node.addEventListener('error',failed,{once:true});node.setAttribute('src',source);
}

function offscreenLazy(record){
 if(record.attribute!=='src'||record.node.loading!=='lazy')return false;
 const box=record.node.getBoundingClientRect();
 return !record.node.getClientRects().length||box.bottom<=0||box.top>=innerHeight;
}

async function refreshOnce(force){
 const version=await deploymentVersion();
 if(pageVersion===null)pageVersion=document.querySelector('meta[name="electronicama-version"]')?.content||version;
 pruneFailures(version);
 if(assetRevision?.version!==version&&(assetRevision||version!==pageVersion))assetRevision={version,token:null};
 if(!assetRevision&&!force&&!failures.size)return {version,changed:0,failed:0};
 const refreshToken=force||failures.size?Date.now()+'-'+(++batch):null;
 if(force)assetRevision={version,token:refreshToken};
 const token=assetRevision?.token||null,groups=new Map();
 for(const node of document.querySelectorAll('img[src],link[rel~="icon"][href],link[rel~="apple-touch-icon"][href]')){
  // A responsive picture owns its own source selection and is left to its
  // component. Public emblems currently use a single static image source.
  if(node.tagName==='IMG'&&(node.hasAttribute('srcset')||node.closest('picture')))continue;
  const attribute=node.tagName==='IMG'?'src':'href',original=node.getAttribute(attribute),url=assetURL(original);
  if(!url)continue;
  const retry=failures.get(node);
  if(!force&&!retry&&url.searchParams.get('v')===version&&(!token||url.searchParams.get('refresh')===token))continue;
  url.searchParams.set('v',version);
  if(token)url.searchParams.set('refresh',token);
  if(retry)url.searchParams.set('retry',refreshToken);
  const source=url.href,record={node,attribute,original};
  if(!groups.has(source))groups.set(source,[]);groups.get(source).push(record);
 }
 let changed=0;
 await Promise.all([...groups].map(async([source,records])=>{
  const eager=records.some(record=>!offscreenLazy(record));
  if(eager){
   try{await preload(source);}catch{
    for(const record of records)if(current(record))failures.set(record.node,{attribute:record.attribute,original:record.original,version});
    return;
   }
  }
  for(const record of records){
   if(!current(record))continue;
   failures.delete(record.node);
   if(!eager)deferLazy(record,source,version);
   else{lazyLoads.get(record.node)?.cleanup();record.node.setAttribute(record.attribute,source);}
   changed++;
  }
 }));
 pruneFailures(version);
 return {version,changed,failed:failures.size};
}

export function refreshAdminEmblems({force=false}={}){
 forcePending=forcePending||Boolean(force);
 if(inFlight)return inFlight;
 inFlight=(async()=>{
  let result;
  do{
   const requestedForce=forcePending;forcePending=false;
   try{result=await refreshOnce(requestedForce);}catch(error){if(!forcePending)throw error;}
  }while(forcePending);
  return result;
 })().finally(()=>{inFlight=null;});
 return inFlight;
}
