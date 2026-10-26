/* Speech starts only from a user's sticker click; no microphone is needed. */
let player=null,revision=0;
export async function playStickerSound(id,button,knownPhrase){
 if(!/^[a-z0-9_-]{1,60}$/.test(id))return;
 const current=++revision;player?.pause();window.speechSynthesis?.cancel();
 if(button)button.disabled=true;
 try{
  let phrase=knownPhrase;
  if(!phrase){const response=await fetch('/api/stickers/'+encodeURIComponent(id)+'/phrase');if(!response.ok)throw Error();phrase=(await response.json()).phrase;}
  if(current!==revision)return;
  if('speechSynthesis' in window&&'SpeechSynthesisUtterance' in window){
   const speech=new SpeechSynthesisUtterance(phrase);speech.lang='es-ES';speech.rate=.96;speech.volume=.7;
   const voice=speechSynthesis.getVoices().find(v=>v.lang==='es-ES')||speechSynthesis.getVoices().find(v=>v.lang.startsWith('es'));
   if(voice)speech.voice=voice;
   speech.onerror=event=>{if(current!==revision||['canceled','interrupted'].includes(event.error))return;if(button){button.title='La voz no está disponible. Puedes leer: '+phrase;button.setAttribute('aria-label',phrase+' · voz no disponible');}};
   speechSynthesis.speak(speech);
   if(button){button.title=phrase;button.setAttribute('aria-label','Frase del sticker: '+phrase);}
  }else{
   if(!player){player=new Audio();player.preload='none';player.volume=.35;}
   player.src='/api/stickers/'+encodeURIComponent(id)+'/sound.wav';await player.play();
   if(button){button.title='Tu dispositivo no ofrece voz. '+phrase;button.setAttribute('aria-label',phrase+' · sonido alternativo');}
  }
 }catch{if(button){button.title='No se pudo reproducir. Pulsa para reintentar.';button.setAttribute('aria-label','Reintentar frase del sticker');}}
 finally{if(button)button.disabled=false;}
}
window.OlStickerAudio={play:playStickerSound};
window.addEventListener('pagehide',()=>{revision++;player?.pause();window.speechSynthesis?.cancel();});
