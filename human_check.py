"""Single-use, session-bound visual checks for limited founder reservations."""
import base64,hashlib,io,secrets
from datetime import timedelta
from flask import Blueprint,jsonify,session
from PIL import Image,ImageDraw,ImageFont
from membership import database,now_utc,stamp,payload,get_user,allow_attempt
bp=Blueprint('human_check',__name__)
ALPHABET='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
def new_code():return ''.join(secrets.choice(ALPHABET) for _ in range(5))
def digest(nonce,code):return hashlib.sha256((nonce+':'+code.upper().strip()).encode()).hexdigest()

def verify(conn):
 data=payload();nonce=str(data.get('human_id',''));answer=str(data.get('human_answer',''))
 if len(nonce)!=32 or len(answer)>12:return False
 row=conn.execute('SELECT answer_hash,session_hash,expires_at FROM human_challenges WHERE id=?',(nonce,)).fetchone()
 if not row:return False
 conn.execute('DELETE FROM human_challenges WHERE id=?',(nonce,))
 return row['expires_at']>stamp(now_utc()) and secrets.compare_digest(row['session_hash'],hashlib.sha256(session.get('csrf','').encode()).hexdigest()) and secrets.compare_digest(row['answer_hash'],digest(nonce,answer))

@bp.get('/api/account/human-check')
def challenge():
 if not allow_attempt('human-check',30):return jsonify(error='Espera unos minutos antes de pedir otro código.'),429
 from membership import csrf_token
 csrf_token()
 code=new_code();nonce=secrets.token_hex(16);image=Image.new('RGB',(260,90),'#f4f0e6');draw=ImageDraw.Draw(image)
 try:font=ImageFont.truetype('DejaVuSans-Bold.ttf',36)
 except OSError:font=ImageFont.load_default(size=36)
 for _ in range(140):
  x,y=secrets.randbelow(260),secrets.randbelow(90);draw.ellipse((x,y,x+2,y+2),fill='#bdb6a6')
 for i,char in enumerate(code):draw.text((20+i*45,18+secrets.randbelow(12)),char,font=font,fill='#35405b',stroke_width=1)
 for _ in range(4):draw.line((0,secrets.randbelow(90),260,secrets.randbelow(90)),fill='#c6b885',width=1)
 output=io.BytesIO();image.save(output,format='PNG')
 with database() as conn:
  conn.execute('DELETE FROM human_challenges WHERE expires_at<=?',(stamp(now_utc()),))
  conn.execute('INSERT INTO human_challenges(id,answer_hash,session_hash,expires_at) VALUES(?,?,?,?)',(nonce,digest(nonce,code),hashlib.sha256(session['csrf'].encode()).hexdigest(),stamp(now_utc()+timedelta(minutes=5))))
 return jsonify(id=nonce,image='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode(),expires_seconds=300)

def install(app):
 if bp.name not in app.blueprints:app.register_blueprint(bp)
