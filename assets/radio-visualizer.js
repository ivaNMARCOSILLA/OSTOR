/* A small radio display. Capturing a copy never reroutes the audible media. */
(()=>{
 'use strict';
 const BAR_COUNT=14,FRAME_MS=60,SILENCE_MS=900;
 let mount=null,status=null,bars=[],levels=new Array(BAR_COUNT).fill(0),media=null;
 let source='',playing=false,mode='playback',frame=0,lastFrame=0,lastSignal=0;
 let context=null,stream=null,input=null,analyser=null,frequencies=null,destroyed=false;
 const mediaEvents=[],streamEvents=[];
 const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)');
 const text=value=>window.OlLocale?.t(value)||value;
 function ensureMount(){
  if(mount?.isConnected)return true;
  mount=document.getElementById('radio-visualizer');if(!mount)return false;
  mount.classList.add('radio-visualizer');
  const label=document.createElement('span');label.className='radio-visualizer-label';label.textContent=text('RITMO');
  const display=document.createElement('div');display.className='radio-visualizer-bars';display.setAttribute('aria-hidden','true');
  bars=[];
  for(let i=0;i<BAR_COUNT;i++){
   const bar=document.createElement('span');bar.className='radio-visualizer-bar';
   bar.style.setProperty('--radio-level','0');bar.style.setProperty('--radio-delay',(-i*.087)+'s');bar.style.setProperty('--radio-duration',(.65+(i%5)*.13)+'s');
   display.append(bar);bars.push(bar);
  }
  status=document.createElement('span');status.className='radio-visualizer-status';
  mount.replaceChildren(label,display,status);return true;
 }
 function changeStatus(value){const next=text(value);if(status&&status.textContent!==next)status.textContent=next;}
 function resetBars(){
  for(let i=0;i<bars.length;i++)if(levels[i]!==0){levels[i]=0;bars[i].style.setProperty('--radio-level','0');}
 }
 function visible(){return !document.hidden&&mount?.isConnected&&!mount.closest('[hidden],.hidden');}
 function canAnimate(){return !destroyed&&playing&&visible()&&!reduced?.matches;}
 function stopFrames(){cancelAnimationFrame(frame);frame=0;lastFrame=0;}
 function suspend(){if(context?.state==='running')context.suspend().catch(()=>{});}
 function releaseCapture(){
  for(const [target,name,listener] of streamEvents)target.removeEventListener(name,listener);
  streamEvents.length=0;
  try{input?.disconnect();}catch{}
  try{analyser?.disconnect();}catch{}
  // These are the copy's tracks, never the original element's media source.
  try{stream?.getTracks().forEach(track=>track.stop());}catch{}
  stream=null;input=null;analyser=null;frequencies=null;lastSignal=0;mode='playback';
 }
 function listenCapture(target,name,listener){target.addEventListener(name,listener);streamEvents.push([target,name,listener]);}
 function connectCapture(){
  if(destroyed||!media||analyser||!playing||reduced?.matches||document.hidden)return;
  const capture=media.captureStream||media.mozCaptureStream;
  const AudioContext=window.AudioContext||window.webkitAudioContext;
  if(typeof capture!=='function'||!AudioContext)return;
  try{
   if(!stream){
    stream=capture.call(media);
    const reconnect=()=>{try{input?.disconnect();}catch{}input=null;analyser=null;frequencies=null;mode='playback';connectCapture();refresh();};
    listenCapture(stream,'addtrack',reconnect);listenCapture(stream,'removetrack',reconnect);
   }
   const tracks=stream.getAudioTracks();if(!tracks.length)return;
   if(!context||context.state==='closed')context=new AudioContext();
   // A separate captured MediaStream feeds only an analyser. No destination,
   // MediaElementSource, crossOrigin mutation, microphone or proxy is involved.
   const node=context.createMediaStreamSource(stream),meter=context.createAnalyser();
   meter.fftSize=256;meter.smoothingTimeConstant=.72;node.connect(meter);
   input=node;analyser=meter;frequencies=new Uint8Array(meter.frequencyBinCount);
   lastSignal=performance.now();
   context.resume().catch(()=>{});
  }catch{releaseCapture();}
 }
 function paintFrame(time){
  frame=0;if(!canAnimate()){refresh();return;}
  if(!analyser||!frequencies)return;
  if(time-lastFrame>=FRAME_MS){
   lastFrame=time;
   try{
    analyser.getByteFrequencyData(frequencies);
    let peak=0;for(const value of frequencies)peak=Math.max(peak,value);
    if(peak>2){mode='levels';lastSignal=time;}
    else if(time-lastSignal>SILENCE_MS)mode='playback';
    mount.dataset.mode=mode;
    changeStatus(mode==='levels'?'Nivel de audio':'Indicador de reproducción');
    if(mode==='levels'){
     const nyquist=context.sampleRate/2;
     for(let i=0;i<BAR_COUNT;i++){
      const from=Math.max(1,Math.floor(70*Math.pow(100,i/BAR_COUNT)/nyquist*frequencies.length));
      const until=Math.min(frequencies.length,Math.max(from+1,Math.ceil(70*Math.pow(100,(i+1)/BAR_COUNT)/nyquist*frequencies.length)));
      let sum=0;for(let n=from;n<until;n++)sum+=frequencies[n];
      const value=Math.min(1,Math.pow((sum/Math.max(1,until-from))/235,.85));
      const next=Math.max(0,levels[i]*.45+value*.55);
      if(Math.abs(next-levels[i])>.018){levels[i]=next;bars[i].style.setProperty('--radio-level',next.toFixed(3));}
     }
    }else resetBars();
   }catch{releaseCapture();refresh();return;}
  }
  frame=requestAnimationFrame(paintFrame);
 }
 function refresh(){
  if(destroyed||!ensureMount())return;
  const animated=canAnimate();
  mount.dataset.source=source;mount.dataset.state=playing?'playing':source?'paused':'idle';mount.dataset.animate=String(animated);
  if(!animated){stopFrames();suspend();resetBars();mount.dataset.mode='playback';changeStatus(playing?'Indicador de reproducción':source?'En pausa':'Selecciona música');return;}
  if(source==='AUDIO'){connectCapture();if(context?.state==='suspended')context.resume().catch(()=>{});}
  mount.dataset.mode=analyser?mode:'playback';
  changeStatus(analyser&&mode==='levels'?'Nivel de audio':'Indicador de reproducción');
  if(analyser&&!frame)frame=requestAnimationFrame(paintFrame);
 }
 function unbindMedia(){
  for(const [name,listener] of mediaEvents)media?.removeEventListener(name,listener);
  mediaEvents.length=0;releaseCapture();media=null;
 }
 function setMedia(next){
  if(destroyed)return;
  if(next&&next===media){refresh();return;}
  unbindMedia();stopFrames();resetBars();source=next?'AUDIO':'';playing=false;media=next||null;
  if(media){
   const changed=event=>{
    if(event.type==='emptied'){releaseCapture();playing=false;}
    else if(['pause','ended','waiting','stalled','error'].includes(event.type))playing=false;
    else if(event.type==='playing')playing=!media.paused&&!media.ended;
    else playing=!media.paused&&!media.ended&&media.readyState>=2;
    refresh();
   };
   for(const name of ['playing','pause','ended','waiting','stalled','error','emptied','loadedmetadata','canplay']){media.addEventListener(name,changed);mediaEvents.push([name,changed]);}
   playing=!media.paused&&!media.ended&&media.readyState>=2;
  }
  refresh();
 }
 function setPlayback(state={}){
  if(destroyed)return;
  const nextSource=state.source==='YOUTUBE'?'YOUTUBE':state.source==='AUDIO'?'AUDIO':source;
  if(nextSource==='YOUTUBE'&&media)unbindMedia();
  source=nextSource;playing=Boolean(state.playing);refresh();
 }
 function background(){stopFrames();suspend();resetBars();if(mount)mount.dataset.animate='false';}
 function destroy(){
  destroyed=true;stopFrames();unbindMedia();resetBars();
  document.removeEventListener('visibilitychange',refresh);window.removeEventListener('pageshow',refresh);window.removeEventListener('pagehide',background);
  reduced?.removeEventListener?.('change',refresh);
  if(context&&context.state!=='closed')context.close().catch(()=>{});
  context=null;if(mount){mount.dataset.state='idle';mount.dataset.mode='playback';mount.dataset.animate='false';}changeStatus('Selecciona música');
 }
 document.addEventListener('visibilitychange',refresh);window.addEventListener('pageshow',refresh);window.addEventListener('pagehide',background);reduced?.addEventListener?.('change',refresh);
 window.OlRadioVisualizer={setMedia,setPlayback,destroy};
 refresh();
})();
