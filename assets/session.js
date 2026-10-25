/* Public catalogue, paid playback. Server authorization remains authoritative. */
(() => {
  let token='',memberId='',active=false,initialized=false,welcomeEligible=true;
  const nativeFetch=window.fetch.bind(window);
  function stopMedia(){document.querySelectorAll('audio,video').forEach(media=>{media.pause();media.removeAttribute('src');media.load();});}
  function notify(){const welcome=document.getElementById('unlock-welcome-plan');if(welcome)welcome.classList.toggle('hidden',!welcomeEligible);const button=document.querySelector('#preview-banner [data-unlock]');if(button)button.textContent=welcomeEligible?'DESBLOQUEAR · 1 € / 14 DÍAS ↗':'RENOVAR · 6 € / UN MES ↗';const banner=document.getElementById('preview-banner');if(banner)banner.classList.toggle('hidden',active);window.dispatchEvent(new CustomEvent('maggy:access-changed',{detail:{active}}));}
  function unlock(){if(active)return true;const dialog=document.getElementById('unlock-dialog');if(dialog&&!dialog.open){if(dialog.showModal)dialog.showModal();else dialog.setAttribute('open','');}return false;}
  function lock(){active=false;stopMedia();notify();}
  async function inspect(){
    try{
      const response=await nativeFetch('/api/account/me',{cache:'no-store'});
      if(!response.ok)throw new Error('No se pudo verificar el acceso.');
      const data=await response.json(),nextId=data.user?.id||'visitor',nextActive=Boolean(data.user?.active);
      if(initialized&&nextId!==memberId){lock();location.reload();return {user:null};}
      const changed=!initialized||nextActive!==active;
      token=data.csrf;memberId=nextId;active=nextActive;welcomeEligible=!data.user?.welcome_used;initialized=true;
      if(!active)stopMedia();if(changed)notify();return data;
    }catch{if(!initialized){memberId='visitor';initialized=true;}lock();return {user:null};}
  }
  const ready=inspect();
  window.MaggySession={ready,key:name=>`maggy_member_${memberId}_${name}`,get active(){return active;},requireAccess:unlock,verifyAccess:async()=>{await inspect();return unlock();},fetch:async(url,options={})=>{await ready;const headers=new Headers(options.headers||{});if((options.method||'GET')!=='GET')headers.set('X-CSRF-Token',token);const response=await nativeFetch(url,{...options,headers});if(response.status===401||response.status===402){lock();unlock();}return response;}};
  document.querySelectorAll('[data-unlock]').forEach(button=>button.addEventListener('click',unlock));
  document.getElementById('unlock-close')?.addEventListener('click',()=>document.getElementById('unlock-dialog').close());
  setInterval(inspect,60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)inspect();});
})();

window.addEventListener('pageshow', event => { if(event.persisted) document.dispatchEvent(new Event('visibilitychange')); });
