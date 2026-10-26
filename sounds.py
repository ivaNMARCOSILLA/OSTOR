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
