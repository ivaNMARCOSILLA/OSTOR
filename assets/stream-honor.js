/* A channel distinction never changes the account's name or permissions. */
export function streamHonor(honor){
 if(!honor||typeof honor.alias!=='string'||typeof honor.title!=='string')return null;
 const badge=document.createElement('span'),title=document.createElement('span'),alias=document.createElement('strong');
 badge.className='stream-honor';title.className='stream-honor-title';alias.className='stream-honor-alias';
 const namespace='http://www.w3.org/2000/svg',flower=document.createElementNS(namespace,'svg');
 flower.setAttribute('viewBox','0 0 24 24');flower.setAttribute('aria-hidden','true');flower.setAttribute('focusable','false');flower.classList.add('stream-honor-flower');
 for(let petal=0;petal<6;petal++){const shape=document.createElementNS(namespace,'ellipse');for(const [key,value] of Object.entries({cx:12,cy:6,rx:2.6,ry:4.4,transform:`rotate(${petal*60} 12 12)`}))shape.setAttribute(key,String(value));flower.append(shape);}
 const center=document.createElementNS(namespace,'circle');center.setAttribute('cx','12');center.setAttribute('cy','12');center.setAttribute('r','2');flower.append(center);
 title.textContent=window.OlLocale?.t(honor.title)||honor.title;alias.textContent=honor.alias;alias.translate=false;
 badge.append(flower,title,document.createTextNode(' · '),alias);return badge;
}
