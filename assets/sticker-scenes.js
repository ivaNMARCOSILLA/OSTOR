/* Stable original vector scenes: generated only for the stickers currently visible. */
export function decorateSticker(element,id){
 if(!element||!id)return;
 let seed=2166136261;for(const char of String(id)){seed^=char.charCodeAt(0);seed=Math.imul(seed,16777619)>>>0;}
 const original=seed;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
 const hue=Math.floor(random()*360),second=(hue+35+Math.floor(random()*90))%360,mode=original%6;
 const a=`hsl(${hue} 58% 88%)`,b=`hsl(${second} 64% 77%)`,ink=`hsl(${hue} 48% 48%)`;
 let shapes='';
 for(let i=0;i<12;i++){const x=Math.round(random()*240),y=Math.round(random()*280),size=Math.round(8+random()*40),opacity=(.12+random()*.22).toFixed(2);
  if(mode===0)shapes+=`<circle cx="${x}" cy="${y}" r="${size}" fill="none" stroke="${ink}" stroke-width="2" opacity="${opacity}"/>`;
  else if(mode===1)shapes+=`<path d="M0 ${y} Q60 ${y-size} 120 ${y} T240 ${y}" fill="none" stroke="${ink}" stroke-width="${size/3}" opacity="${opacity}"/>`;
  else if(mode===2)shapes+=`<path d="M${x} ${y-size} l${size/3} ${size/1.5} ${size/1.5} ${size/3} -${size/1.5} ${size/3} -${size/3} ${size/1.5} -${size/3} -${size/1.5} -${size/1.5} -${size/3} ${size/1.5} -${size/3} Z" fill="${ink}" opacity="${opacity}"/>`;
  else if(mode===3)shapes+=`<ellipse cx="${x}" cy="${y}" rx="${size/2}" ry="${size}" transform="rotate(${Math.floor(random()*180)} ${x} ${y})" fill="${ink}" opacity="${opacity}"/>`;
  else if(mode===4)shapes+=`<path d="M${x} ${y-size} l${size} ${size} -${size} ${size} -${size} -${size} Z" fill="none" stroke="${ink}" stroke-width="2" opacity="${opacity}"/>`;
  else shapes+=`<circle cx="${x}" cy="${y}" r="${size}" fill="${ink}" opacity="${opacity/2}"/><circle cx="${x+size}" cy="${y-size}" r="2" fill="white"/>`;
 }
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 280"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs><path fill="url(#g)" d="M0 0h240v280H0z"/>${shapes}</svg>`;
 element.style.setProperty('--sticker-scene',`url("data:image/svg+xml,${encodeURIComponent(svg)}")`);
 element.style.setProperty('--sticker-scene-delay',`-${original%14000/1000}s`);
 element.dataset.stickerScene=['órbitas','olas','constelación','jardín','cristales','aurora'][mode];
}
