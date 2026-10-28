import * as THREE from './vendor/three/build/three.module.js';
import {OBJLoader} from './vendor/three/examples/jsm/loaders/OBJLoader.js';
import {STLLoader} from './vendor/three/examples/jsm/loaders/STLLoader.js';
const names=['Catenoide','Helicoide','Superficie de Enneper','Botella de Klein','Banda de Möbius','Paraboloide hiperbólico','Pseudoesfera','Malla ondulada','Toroide','Hélice','Esfera','Vórtice','Superficie generativa','Nudo ondulado','Onda polar','Toro deformado'];
const families=['Superficies','Superficies','Superficies','Topologías','Topologías','Curvaturas','Curvaturas','Ondas','Sólidos','Ondas','Sólidos','Ondas','Formas generativas','Formas generativas','Ondas','Topologías'];
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
export function createHolograms(root){
 const $=id=>root.querySelector('#'+id),stage=$('holo-stage'),canvas=$('holo-canvas'),video=$('holo-video'),status=$('holo-status');
 const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'low-power'});
 renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.5));
 const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(45,1,.05,100);camera.position.z=5;
 const group=new THREE.Group();scene.add(group);
 let index=0,wire=true,speed=1,rotate=!matchMedia('(prefers-reduced-motion: reduce)').matches,closed=false,frameId=0,last=0,lastPaint=0,frames=0,assetRevision=0,stream=null,cameraRevision=0,hands=null,inference=false,lastInference=0,tracking=false,handRevision=0;
 let dragX=0,dragY=0,zoom=1;const pointers=new Map();let pinchDistance=0;
 const target=new THREE.Vector3(),position=new THREE.Vector3(),scaleTarget=new THREE.Vector3();stage.dataset.frames='0';stage.dataset.handFrames='0';let handScale=1,handAngle=0;
 const say=message=>{status.textContent=message;};
 function release(object){const geometries=new Set(),materials=new Set(),textures=new Set();object.traverse(item=>{if(item.geometry)geometries.add(item.geometry);for(const material of Array.isArray(item.material)?item.material:[item.material])if(material){materials.add(material);if(material.map)textures.add(material.map);}});for(const texture of textures)texture.dispose();for(const geometry of geometries)geometry.dispose();for(const material of materials)material.dispose();}
 function clear(){release(group);group.clear();}
 function material(color){return new THREE.MeshBasicMaterial({color,wireframe:wire,transparent:true,opacity:.85,side:THREE.DoubleSide});}
 function metadata(){if(index>=239&&index<255)return {name:'Transición al cuadrado · etapa '+(index-238)+'/16',family:'Formas generativas'};const base=index%16,variant=Math.floor(index/16)+1;return {name:index===255?'El cuadrado':names[base]+(variant>1?' · variante '+variant:''),family:index===255?'Planos':families[base]};}
 function update(){const meta=metadata();$('holo-name').textContent=meta.name;$('holo-counter').textContent='Figura '+(index+1)+' de 256';$('holo-family').textContent=meta.family+' · interpretación visual 3D';$('holo-index').value=String(index+1);$('holo-wire').textContent=wire?'Ver sólido':'Ver malla';$('holo-wire').setAttribute('aria-pressed',String(!wire));$('holo-motion').textContent=rotate?'Pausar movimiento':'Activar movimiento';$('holo-motion').setAttribute('aria-pressed',String(rotate));}
 function point(u,v){const a=u*Math.PI*2,b=v*Math.PI*2,x=(u-.5)*2,y=(v-.5)*2,k=Math.floor(index/16),m=1+k*.018;let r;
  if(index>=239){const t=(index-239)/16,c=Math.cos(a),s=Math.sin(a);return [THREE.MathUtils.lerp(c*(.8+.3*Math.cos(b)),Math.sign(c)*Math.pow(Math.abs(c),1-t*.85)*1.2,t),THREE.MathUtils.lerp(s*(.8+.3*Math.cos(b)),Math.sign(s)*Math.pow(Math.abs(s),1-t*.85)*1.2,t),Math.sin(b)*.4*(1-t)];}
  switch(index%16){
   case 0:return [Math.cosh(y*.75)*Math.cos(a)*.75,y*1.15,Math.cosh(y*.75)*Math.sin(a)*.75];
   case 1:return [x*Math.cos(y*Math.PI*2)*1.1,y*1.4,x*Math.sin(y*Math.PI*2)*1.1];
   case 2:return [(x-x*x*x/3+x*y*y)*.5,(y-y*y*y/3+y*x*x)*.5,(x*x-y*y)*.5];
   case 3:r=.85+Math.cos(a/2)*Math.sin(b)-Math.sin(a/2)*Math.sin(2*b);return [r*Math.cos(a)*.7,(Math.sin(a/2)*Math.sin(b)+Math.cos(a/2)*Math.sin(2*b))*.7,r*Math.sin(a)*.7];
   case 4:r=1+y*.45*Math.cos(a/2);return [r*Math.cos(a),y*.45*Math.sin(a/2),r*Math.sin(a)];
   case 5:return [x*1.3,(x*x-y*y)*.65,y*1.3];
   case 6:{const t=clamp(v,.08,.92)*Math.PI*1.8-Math.PI*.9;r=1/Math.cosh(t);return [r*Math.cos(a)*1.2,(t-Math.tanh(t))*1.2,r*Math.sin(a)*1.2];}
   case 7:return [x*1.3,Math.sin(x*Math.PI*(3+k*.1))*Math.cos(y*Math.PI*3)*.3,y*1.3];
   case 8:r=1+.3*Math.cos(b);return [r*Math.cos(a),.3*Math.sin(b),r*Math.sin(a)];
   case 9:r=.55+.2*Math.cos(b*3);return [r*Math.cos(x*12),x*1.6,r*Math.sin(x*12)];
   case 10:return [Math.cos(y*Math.PI/2)*Math.cos(a)*1.2,Math.sin(y*Math.PI/2)*1.2,Math.cos(y*Math.PI/2)*Math.sin(a)*1.2];
   case 11:r=.2+v*1.1;return [r*Math.cos(-a*2),(v-.5)*1.7,r*Math.sin(-a*2)];
   case 12:r=.8+.25*Math.sin(x*6)*Math.cos(y*6);return [r*Math.cos(a),Math.sin(x*4)*.45,r*Math.sin(a)];
   case 13:r=.8+.3*Math.cos(a*3)*Math.sin(b*3);return [r*Math.cos(a),Math.sin(b*2)*.7,r*Math.sin(a)];
   case 14:return [x*1.3,Math.sin(x*9*m)*Math.sin(y*9)*.3,y*1.3];
   default:r=.85+.3*Math.sin((a+b)*2);return [r*Math.cos(a),Math.sin(b*3)*.5,r*Math.sin(a)];
  }
 }
 function build(){clear();const color=new THREE.Color().setHSL((index*.079+.48)%1,.9,.63);if(index===255){group.add(new THREE.Mesh(new THREE.PlaneGeometry(2.6,2.6),material(0xffffff)));group.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-1.3,-1.3,0),new THREE.Vector3(1.3,-1.3,0),new THREE.Vector3(1.3,1.3,0),new THREE.Vector3(-1.3,1.3,0)]),new THREE.LineBasicMaterial({color:0x9ce8ff})));return;}
  const n=32,vertices=[],indices=[];for(let i=0;i<=n;i++)for(let j=0;j<=n;j++){const p=point(i/n,j/n),variant=Math.floor(index/16);vertices.push(p[0]*(1+variant*.012),p[1],p[2]*(1+variant*.018));}
  for(let i=0;i<n;i++)for(let j=0;j<n;j++){const a=i*(n+1)+j,b=a+n+1;indices.push(a,b,a+1,b,b+1,a+1);}
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.setIndex(indices);geometry.computeVertexNormals();group.add(new THREE.Mesh(geometry,material(color)));
 }
 function choose(value){assetRevision++;$('holo-wire').disabled=false;index=(Number(value)+256)%256;build();update();say('Usa el ratón o un dedo para girar la figura.');}
 function reset(){dragX=0;dragY=0;zoom=1;target.set(0,0,0);position.set(0,0,0);handScale=1;handAngle=0;group.rotation.set(0,0,0);}
 const listeners=[];function on(node,type,fn,options){node.addEventListener(type,fn,options);listeners.push(()=>node.removeEventListener(type,fn,options));}
 on($('holo-prev'),'click',()=>choose(index-1));on($('holo-next'),'click',()=>choose(index+1));on($('holo-square'),'click',()=>choose(255));on($('holo-index'),'input',event=>choose(clamp(Number(event.target.value),1,256)-1));
 on($('holo-reset'),'click',reset);on($('holo-wire'),'click',()=>{wire=!wire;group.traverse(item=>{if(item.isMesh&&!item.material.map)item.material.wireframe=wire;});update();});on($('holo-motion'),'click',()=>{rotate=!rotate;update();});on($('holo-speed'),'input',event=>{speed=clamp(Number(event.target.value),0,2);});
 on($('holo-globe'),'click',()=>{assetRevision++;$('holo-wire').disabled=false;$('holo-counter').textContent='Globo';clear();group.add(new THREE.Mesh(new THREE.SphereGeometry(1.25,32,20),material(0x64dfff)));const points=[];for(let i=0;i<100;i++)points.push(new THREE.Vector3(Math.cos(i/100*Math.PI*2)*1.5,0,Math.sin(i/100*Math.PI*2)*1.5));group.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:0xe7c579})));$('holo-name').textContent='Globo terráqueo';$('holo-family').textContent='Esfera y anillo · representación abstracta';say('Globo preparado. Puedes girarlo con el ratón o el dedo.');});
 on(canvas,'keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End',' '].includes(event.key)){event.preventDefault();event.stopPropagation();if(event.key==='ArrowLeft')choose(index-1);if(event.key==='ArrowRight')choose(index+1);if(event.key==='End')choose(255);if(event.key==='Home')reset();if(event.key===' '){rotate=!rotate;update();}}});
 on(canvas,'pointerdown',event=>{canvas.setPointerCapture(event.pointerId);pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});canvas.focus({preventScroll:true});});
 on(canvas,'pointermove',event=>{if(!pointers.has(event.pointerId))return;const old=pointers.get(event.pointerId);pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});if(pointers.size===1){dragY+=(event.clientX-old.x)*.008;dragX+=(event.clientY-old.y)*.008;pinchDistance=0;}else{const [a,b]=[...pointers.values()];const distance=Math.hypot(a.x-b.x,a.y-b.y);if(pinchDistance)zoom=clamp(zoom*distance/pinchDistance,.4,2.5);pinchDistance=distance;}});
 for(const name of ['pointerup','pointercancel','lostpointercapture'])on(canvas,name,event=>{pointers.delete(event.pointerId);pinchDistance=0;});
 on(canvas,'wheel',event=>{if(!event.ctrlKey)return;event.preventDefault();zoom=clamp(zoom-event.deltaY*.002,.4,2.5);},{passive:false});
 async function upload(file){if(!file)return;const revision=++assetRevision;let object=null,url=null;
  try{
   if(file.size>5*1024*1024)throw Error('El archivo supera los 5 MB.');const ext=file.name.split('.').pop().toLowerCase();
   if(ext==='obj'){const text=await file.text();let triangles=0,vertices=0;for(const line of text.split(/\r?\n/)){if(/^v\s/.test(line))vertices++;if(/^f\s/.test(line)){const count=line.trim().split(/\s+/).length-1;if(count>32)throw Error('El OBJ contiene caras demasiado complejas.');triangles+=Math.max(0,count-2);}}if(vertices>100000||triangles>60000)throw Error('Reduce el modelo a 60.000 triángulos.');object=new OBJLoader().parse(text);}
   else if(ext==='stl'){const buffer=await file.arrayBuffer();const data=new DataView(buffer);const binary=buffer.byteLength>=84&&84+data.getUint32(80,true)*50===buffer.byteLength;if(binary&&data.getUint32(80,true)>60000)throw Error('Reduce el STL a 60.000 triángulos.');if(!binary&&!/^\s*solid\b/i.test(new TextDecoder().decode(buffer.slice(0,100))))throw Error('El archivo STL está incompleto o no es válido.');if(!binary&&((new TextDecoder().decode(buffer).match(/vertex\s/gi)||[]).length>180000))throw Error('Reduce el STL a 60.000 triángulos.');object=new THREE.Mesh(new STLLoader().parse(buffer),material(0x80eaff));}
   else if(['png','jpg','jpeg','webp'].includes(ext)){url=URL.createObjectURL(file);const image=new Image();image.src=url;await image.decode();if(image.naturalWidth*image.naturalHeight>16777216||image.naturalWidth>4096||image.naturalHeight>4096)throw Error('La imagen es demasiado grande; usa hasta 16 megapíxeles.');const texture=new THREE.Texture(image);texture.colorSpace=THREE.SRGBColorSpace;texture.needsUpdate=true;object=new THREE.Mesh(new THREE.PlaneGeometry(2.8,2.8*image.naturalHeight/image.naturalWidth),new THREE.MeshBasicMaterial({map:texture,transparent:true,side:THREE.DoubleSide}));}
   else throw Error('Elige un archivo OBJ, STL, PNG, JPG o WebP.');
   if(closed||revision!==assetRevision){release(object);return;}
   let count=0;object.traverse(item=>{const positions=item.geometry?.getAttribute('position');if(positions&&!positions.array.every(Number.isFinite))throw Error('El modelo contiene coordenadas no válidas.');count+=positions?.count||0;});if(!count||count>250000)throw Error('El archivo no contiene un modelo compatible o es demasiado complejo.');
   if(ext==='obj')object.traverse(item=>{if(item.isMesh){for(const old of Array.isArray(item.material)?item.material:[item.material])old?.dispose();item.material=material(0x80eaff);}});
   if(['obj','stl'].includes(ext)){const box=new THREE.Box3().setFromObject(object),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());const wrapper=new THREE.Group();object.position.sub(center);wrapper.add(object);wrapper.scale.setScalar(2.5/Math.max(size.x,size.y,size.z,.01));object=wrapper;}
   clear();group.add(object);reset();$('holo-wire').disabled=!['obj','stl'].includes(ext);$('holo-counter').textContent='Archivo local';$('holo-name').textContent=file.name;$('holo-family').textContent='Archivo local · no se sube al servidor';say('Archivo abierto solo en este navegador.');
  }catch(error){if(object)release(object);if(!closed&&revision===assetRevision)say('No se pudo abrir: '+error.message);}
  finally{if(url)URL.revokeObjectURL(url);$('holo-file').value='';}
 }
 on($('holo-file'),'change',event=>upload(event.target.files[0]));
 function stopHands(){handRevision++;tracking=false;const old=hands;hands=null;if(old){try{Promise.resolve(old.close()).catch(()=>{});}catch{}}$('holo-hands').textContent='Activar control con la mano';$('holo-hands').setAttribute('aria-pressed','false');target.set(0,0,0);handScale=1;handAngle=0;}
 function stopCamera(){cameraRevision++;stopHands();if(stream)stream.getTracks().forEach(track=>track.stop());stream=null;video.srcObject=null;video.hidden=true;$('holo-camera').textContent='Activar cámara';$('holo-camera').disabled=false;$('holo-hands').disabled=true;}
 async function startCamera(){if(stream){stopCamera();say('Cámara apagada.');return;}const revision=++cameraRevision;$('holo-camera').disabled=true;
  try{if(!navigator.mediaDevices?.getUserMedia)throw Error('Este navegador no permite activar la cámara aquí.');const media=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:640},height:{ideal:480}},audio:false});if(closed||document.hidden||revision!==cameraRevision){media.getTracks().forEach(track=>track.stop());return;}stream=media;video.srcObject=media;await video.play();video.hidden=false;$('holo-camera').textContent='Apagar cámara';$('holo-hands').disabled=false;say('Cámara privada activa. Puedes activar el control con la mano.');}
  catch(error){if(!closed&&revision===cameraRevision){stopCamera();say(error.name==='NotAllowedError'?'Permiso de cámara no concedido. Puedes seguir usando ratón y botones.':'No se pudo activar la cámara. Puedes seguir usando ratón y botones.');}}
  finally{if(!closed&&revision===cameraRevision)$('holo-camera').disabled=false;}
 }
 on($('holo-camera'),'click',startCamera);
 on($('holo-hands'),'click',async()=>{if(tracking){stopHands();say('Control con la mano desactivado.');return;}if(!stream)return;const revision=++handRevision;$('holo-hands').disabled=true;say('Preparando el control con la mano…');
  try{await loadHands();if(closed||!stream||revision!==handRevision)return;hands=new window.Hands({locateFile:file=>'/assets/vendor/hands/'+file});hands.setOptions({maxNumHands:1,modelComplexity:0,minDetectionConfidence:.7,minTrackingConfidence:.7});hands.onResults(result=>{if(!tracking||closed||revision!==handRevision)return;stage.dataset.handFrames=String(Number(stage.dataset.handFrames||0)+1);const points=result.multiHandLandmarks?.[0];if(!points){target.set(0,0,0);return;}const center=[0,5,9,13,17].map(i=>points[i]);const x=center.reduce((a,p)=>a+p.x,0)/5,y=center.reduce((a,p)=>a+p.y,0)/5;target.set(clamp((.5-x)*4,-1.5,1.5),clamp((.5-y)*3,-1,1),0);handScale=clamp(Math.hypot(points[4].x-points[8].x,points[4].y-points[8].y)*5,.5,1.8);handAngle=-(Math.atan2(points[9].y-points[0].y,points[9].x-points[0].x)+Math.PI/2);});tracking=true;$('holo-hands').textContent='Desactivar control con la mano';$('holo-hands').setAttribute('aria-pressed','true');say('Mueve la mano delante de la cámara; separa pulgar e índice para cambiar el tamaño.');}
  catch{stopHands();if(!closed)say('El seguimiento no está disponible. La cámara y el control manual siguen funcionando.');}
  finally{if(!closed)$('holo-hands').disabled=!stream;}
 });
 function resize(){if(closed)return;const width=Math.max(1,stage.clientWidth),height=Math.max(1,stage.clientHeight);renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();}
 const observer=new ResizeObserver(resize);observer.observe(stage);
 function frame(now){if(closed||document.hidden){frameId=0;return;}frameId=requestAnimationFrame(frame);if(now-lastPaint<32)return;const delta=Math.min((now-last)/1000,.1);last=now;lastPaint=now;
  position.lerp(target,.12);group.position.copy(position);if(rotate)group.rotation.y+=delta*.6*speed;group.rotation.x=dragX;group.rotation.z=handAngle;group.rotation.y+=dragY;dragY=0;group.scale.lerp(scaleTarget.setScalar(zoom*handScale),.15);renderer.render(scene,camera);stage.dataset.frames=String(++frames);
  if(tracking&&hands&&!inference&&video.readyState>=2&&now-lastInference>100){lastInference=now;inference=true;const activeHands=hands,activeRevision=handRevision;try{Promise.resolve(activeHands.send({image:video})).catch(()=>{if(!closed&&hands===activeHands&&handRevision===activeRevision){stopHands();say('El seguimiento se ha detenido. Puedes usar el control manual.');}}).finally(()=>{inference=false;});}catch{inference=false;stopHands();}}
 }
 on(document,'visibilitychange',()=>{if(document.hidden){stopCamera();cancelAnimationFrame(frameId);frameId=0;}else if(!frameId&&!closed){last=performance.now();frameId=requestAnimationFrame(frame);}});
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');on(reduced,'change',event=>{if(event.matches){rotate=false;update();}});
 on(canvas,'webglcontextlost',event=>{event.preventDefault();stopCamera();cancelAnimationFrame(frameId);frameId=0;say('Se ha detenido la vista 3D. Cierra Hologramas y vuelve a abrirlo.');});
 build();update();resize();say('Arrastra para girar. La cámara está apagada.');last=performance.now();frameId=requestAnimationFrame(frame);
 return {dispose(){if(closed)return;closed=true;assetRevision++;stopCamera();cancelAnimationFrame(frameId);observer.disconnect();listeners.forEach(remove=>remove());clear();renderer.dispose();renderer.forceContextLoss();canvas.replaceWith(canvas.cloneNode(false));pointers.clear();}};
}
let handsLoading=null;
function loadHands(){if(window.Hands)return Promise.resolve();if(handsLoading)return handsLoading;handsLoading=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/assets/vendor/hands/hands.js';const timer=setTimeout(()=>{script.remove();handsLoading=null;reject(Error('timeout'));},15000);script.onload=()=>{clearTimeout(timer);if(window.Hands)resolve();else{handsLoading=null;reject(Error('sdk'));}};script.onerror=()=>{clearTimeout(timer);script.remove();handsLoading=null;reject(Error('sdk'));};document.head.append(script);});return handsLoading;}
