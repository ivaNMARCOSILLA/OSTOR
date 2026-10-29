"""Small original positive sound signatures, synthesized on demand without downloads."""
import hashlib
import io
import math
import struct
import wave
from functools import lru_cache
from flask import Blueprint,Response,current_app,jsonify
from membership import database

bp=Blueprint('sounds',__name__)

@lru_cache(maxsize=128)
def sound_bytes(ident):
 seed=int.from_bytes(hashlib.sha256(ident.encode()).digest()[:8],'big');rate=16000;duration=.72
 notes=[0,2,4,7,9,12,14,16];base=[220,246.9417,261.6256,293.6648,329.6276][seed%5]
 events=[]
 for i in range(4):
  note=notes[(seed>>(i*3+4))&7];start=i*.145+((seed>>(i*2+24))&3)*.004
  events.append((start,base*2**(note/12),.17+((seed>>(i*2+36))&3)*.008))
 samples=bytearray()
 for index in range(int(rate*duration)):
  t=index/rate;value=0.0
  for start,frequency,length in events:
   x=t-start
   if 0<=x<length:
    envelope=min(1,x/.012)*(1-x/length)**1.7
    harmonic=.08+((seed>>48)&7)*.012
    value+=(math.sin(2*math.pi*frequency*x)+harmonic*math.sin(4*math.pi*frequency*x))*envelope*.17
  samples.extend(struct.pack('<h',round(max(-.32,min(.32,value))*32767)))
 output=io.BytesIO()
 with wave.open(output,'wb') as stream:stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(rate);stream.writeframes(samples)
 return output.getvalue()


def response_for(ident):
 limiter=current_app.extensions.get('streamer_rate_limiter')
 if limiter and not limiter('sticker-sounds',150):return jsonify(error='Espera un momento antes de escuchar más sonidos.'),429
 return Response(sound_bytes(ident),mimetype='audio/wav',headers={'Cache-Control':'public, max-age=86400','X-Content-Type-Options':'nosniff'})

@bp.get('/api/stickers/<ident>/phrase')
def sticker_phrase(ident):
 from rewards import catalog
 from sticker_phrases import phrase_for
 if not any(item['id']==ident for item in catalog(0)):return jsonify(error='Este sticker no existe.'),404
 return jsonify(phrase=phrase_for(ident),language='es-ES')

@bp.get('/api/stickers/<ident>/sound.wav')
def sticker_sound(ident):
 from rewards import catalog
 if not any(item['id']==ident for item in catalog(0)):return jsonify(error='Este sticker no existe.'),404
 return response_for('sticker:'+ident)

@bp.get('/api/live/founders/<int:number>/sound.wav')
def founder_sound(number):
 from flask import request
 voice=request.args.get('voice','brisa')
 if voice not in {'brisa','aurora','sonrisa','ritmo','estrellas','celebracion'}:return jsonify(error='Elige un sonido disponible.'),400
 with database() as conn:
  if not conn.execute('SELECT number FROM live_founders WHERE number=?',(number,)).fetchone():return jsonify(error='Esta insignia no existe.'),404
 return response_for(f'founder:{number}:{voice}')

def install(app):app.register_blueprint(bp)

# Optional professional Spanish neural voices. No external calls until explicitly enabled.
NEURAL_VOICES={'female':'es-ES-ElviraNeural','male':'es-ES-AlvaroNeural'}

def neural_voice_spec():
 import os
 provider=os.getenv('OL_STICKER_VOICE_PROVIDER','elevenlabs')
 if provider=='azure':return provider,NEURAL_VOICES
 return provider,{'female':os.getenv('OL_ELEVENLABS_FEMALE_VOICE_ID',''),'male':os.getenv('OL_ELEVENLABS_MALE_VOICE_ID','')}

def neural_voice_ready():
 import os,re
 if os.getenv('OL_STICKER_NEURAL_VOICES')!='1':return False
 provider,voices=neural_voice_spec()
 if provider=='azure':return bool(os.getenv('OL_AZURE_SPEECH_KEY')) and bool(re.fullmatch(r'[a-z0-9-]{2,40}',os.getenv('OL_AZURE_SPEECH_REGION','')))
 return provider=='elevenlabs' and bool(os.getenv('OL_ELEVENLABS_API_KEY')) and all(re.fullmatch(r'[A-Za-z0-9_-]{3,100}',v) for v in voices.values())

@bp.get('/api/stickers/voices')
def sticker_voices():
 provider,_=neural_voice_spec()
 return jsonify(neural_available=neural_voice_ready(),provider='Azure Speech' if provider=='azure' else 'ElevenLabs',language='es-ES',voices=[{'id':'female','name':'Femenina'},{'id':'male','name':'Masculina'}],synthetic=True)

def voice_attempt(member_id,kind,limit):
 from datetime import timedelta
 from membership import now_utc,stamp
 bucket=hashlib.sha256(('sticker-voice:'+kind+':'+member_id).encode()).hexdigest()
 with database() as c:
  c.execute('BEGIN IMMEDIATE');cutoff=stamp(now_utc()-timedelta(minutes=15))
  c.execute('DELETE FROM login_attempts WHERE attempted_at<?',(cutoff,))
  if c.execute('SELECT COUNT(*) AS n FROM login_attempts WHERE bucket=?',(bucket,)).fetchone()['n']>=limit:return False
  c.execute('INSERT INTO login_attempts VALUES(?,?)',(bucket,stamp(now_utc())))
 return True

@bp.post('/api/stickers/<ident>/voice')
def neural_sticker_voice(ident):
 import base64,os,requests
 from datetime import datetime,timedelta
 from xml.sax.saxutils import escape
 from membership import get_user,payload,allow_attempt,now_utc,stamp
 from rewards import catalog
 from sticker_phrases import phrase_for
 user=get_user()
 if not user:return jsonify(error='Inicia sesión para escuchar las voces naturales.'),401
 voice=payload().get('voice','female')
 if not isinstance(voice,str) or voice not in NEURAL_VOICES:return jsonify(error='Selecciona una voz femenina o masculina.'),400
 if not any(item['id']==ident for item in catalog(0)):return jsonify(error='Este sticker no existe.'),404
 if not neural_voice_ready():return jsonify(error='Las voces neuronales están pendientes de conectar. Las voces del dispositivo siguen disponibles.',code='neural_voice_unconfigured'),409
 provider,voices=neural_voice_spec();phrase=phrase_for(ident);key=hashlib.sha256((provider+'-v1:'+voices[voice]+':'+phrase).encode()).hexdigest()
 if not voice_attempt(user['id'],'play',120):return jsonify(error='Espera unos minutos antes de escuchar más frases.'),429
 with database() as c:
  c.execute('BEGIN IMMEDIATE');cached=c.execute('SELECT * FROM sticker_voice_audio WHERE cache_key=?',(key,)).fetchone()
  if cached and cached['audio_base64']:
   return Response(base64.b64decode(cached['audio_base64']),mimetype='audio/mpeg',headers={'Cache-Control':'private, max-age=86400','X-Content-Type-Options':'nosniff'})
  if cached and datetime.fromisoformat(cached['created_at'])>now_utc()-timedelta(seconds=60):return jsonify(pending=True),202
 if not voice_attempt(user['id'],'generation',18):return jsonify(error='Has alcanzado el límite temporal de nuevas frases. Las frases ya preparadas siguen disponibles.'),429
 with database() as c:
  c.execute('BEGIN IMMEDIATE')
  c.execute('DELETE FROM sticker_voice_audio WHERE cache_key=? AND audio_base64 IS NULL AND created_at<?',(key,stamp(now_utc()-timedelta(seconds=60))))
  claimed=c.execute('INSERT INTO sticker_voice_audio(cache_key,created_at) VALUES(?,?) ON CONFLICT(cache_key) DO NOTHING',(key,stamp(now_utc()))).rowcount
 if not claimed:return jsonify(pending=True),202
 try:
  if provider=='azure':
   region=os.environ['OL_AZURE_SPEECH_REGION']
   ssml='<speak version="1.0" xml:lang="es-ES"><voice name="'+voices[voice]+'">'+escape(phrase)+'</voice></speak>'
   response=requests.post('https://'+region+'.tts.speech.microsoft.com/cognitiveservices/v1',headers={'Ocp-Apim-Subscription-Key':os.environ['OL_AZURE_SPEECH_KEY'],'Content-Type':'application/ssml+xml','X-Microsoft-OutputFormat':'audio-24khz-48kbitrate-mono-mp3','User-Agent':'electronicama'},data=ssml.encode(),timeout=(3,15),allow_redirects=False)
  else:
   response=requests.post('https://api.elevenlabs.io/v1/text-to-speech/'+voices[voice],headers={'xi-api-key':os.environ['OL_ELEVENLABS_API_KEY'],'Content-Type':'application/json','Accept':'audio/mpeg'},json={'text':phrase,'model_id':'eleven_multilingual_v2','voice_settings':{'stability':.5,'similarity_boost':.75,'style':.15,'use_speaker_boost':True}},timeout=(3,15),allow_redirects=False)
  if response.status_code!=200 or not response.content or len(response.content)>400000 or not response.headers.get('Content-Type','').lower().startswith(('audio/','application/octet-stream')):raise ValueError('voice provider unavailable')
  audio=response.content
  with database() as c:c.execute('UPDATE sticker_voice_audio SET audio_base64=? WHERE cache_key=?',(base64.b64encode(audio).decode(),key))
  return Response(audio,mimetype='audio/mpeg',headers={'Cache-Control':'private, max-age=86400','X-Content-Type-Options':'nosniff'})
 except (requests.RequestException,ValueError):
  with database() as c:c.execute('DELETE FROM sticker_voice_audio WHERE cache_key=? AND audio_base64 IS NULL',(key,))
  return jsonify(error='La herramienta vocal no responde. Puedes reintentar o elegir una voz del dispositivo.',code='neural_voice_unavailable'),503
