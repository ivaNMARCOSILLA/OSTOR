/* One quiet player shared by sticker sounds: only explicit clicks start audio. */
let player=null,revision=0;
export async function playStickerSound(id,button){
 if(!/^[a-z0-9_-]{1,60}$/.test(id))return;
 const current=++revision;if(!player){player=new Audio();player.preload='none';player.volume=.35;}player.pause();player.src='/api/stickers/'+encodeURIComponent(id)+'/sound.wav';
 if(button)button.disabled=true;
 try{await player.play();if(button&&current===revision)button.setAttribute('aria-label','Sonido del sticker reproducido');}
 catch{if(button){button.title='No se pudo reproducir. Pulsa para reintentar.';button.setAttribute('aria-label','Reintentar sonido del sticker');}}
 finally{if(button)button.disabled=false;}
}
window.OlStickerAudio={play:playStickerSound};
window.addEventListener('pagehide',()=>player?.pause());
