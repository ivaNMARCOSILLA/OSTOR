"""Optional RFC 6238 TOTP with domain-separated server-key derivation and recovery codes."""
import base64,hashlib,hmac,secrets,struct,time
from datetime import timedelta
from urllib.parse import urlencode,quote
from flask import Blueprint,current_app,jsonify,session
from werkzeug.security import check_password_hash
from membership import database,get_user,payload,now_utc,stamp,allow_attempt
bp=Blueprint('two_factor',__name__)

def key_id():
 master=current_app.secret_key
 if isinstance(master,str):master=master.encode()
 return hmac.new(master,b'ol-totp-key-id-v1',hashlib.sha256).hexdigest()

def key_for(member_id,nonce):
 master=current_app.secret_key
 if isinstance(master,str):master=master.encode()
 return hmac.new(master,b'ol-totp-v1\0'+member_id.encode()+b'\0'+nonce.encode(),hashlib.sha256).digest()[:20]

def totp(key,counter):
 digest=hmac.new(key,struct.pack('>Q',counter),hashlib.sha1).digest();offset=digest[-1]&15
 return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)

def counter_now():return int(time.time())//30

def matching_counter(member_id,nonce,code,last=-1):
 code=str(code).replace(' ','').strip()
 if len(code)!=6 or not code.isdigit():return None
 current=counter_now();key=key_for(member_id,nonce)
 for counter in [current,current-1,current+1]:
  if counter>last and counter>=0 and hmac.compare_digest(totp(key,counter),code):return counter
 return None

def recovery_hash(member_id,code):
 master=current_app.secret_key
 if isinstance(master,str):master=master.encode()
 value=''.join(c for c in str(code).upper() if c not in '- ')
 return hmac.new(master,('ol-recovery-v1:'+member_id+':'+value).encode(),hashlib.sha256).hexdigest()

def consume(conn,user,data):
 row=conn.execute('SELECT * FROM member_two_factor WHERE member_id=?',(user['id'],)).fetchone()
 if not row or not row['enabled_at']:return True
 if row['key_id']!=key_id():return False
 counter=matching_counter(user['id'],row['nonce'],data.get('otp',''),row['last_counter'])
 if counter is not None:
  conn.execute('UPDATE member_two_factor SET last_counter=? WHERE member_id=?',(counter,user['id']));return True
 recovery=str(data.get('recovery_code',''))
 if not recovery or len(recovery)>40:return False
 hashed=recovery_hash(user['id'],recovery)
 code=conn.execute('SELECT code_hash FROM two_factor_recovery WHERE member_id=? AND code_hash=? AND used_at IS NULL',(user['id'],hashed)).fetchone()
 if not code:return False
 conn.execute('UPDATE two_factor_recovery SET used_at=? WHERE member_id=? AND code_hash=?',(stamp(now_utc()),user['id'],hashed));return True

def login_factor(user,data):
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');return consume(conn,user,data)

def valid_password(user,data):
 return bool(user and user['password_hash'] and isinstance(data.get('password'),str) and len(data['password'])<=256 and check_password_hash(user['password_hash'],data['password']))

@bp.get('/api/account/2fa/status')
def status():
 user=get_user()
 if not user:return jsonify(error='Entra en tu cuenta.'),401
 with database() as conn:
  row=conn.execute('SELECT enabled_at FROM member_two_factor WHERE member_id=?',(user['id'],)).fetchone()
  unused=conn.execute('SELECT COUNT(*) AS n FROM two_factor_recovery WHERE member_id=? AND used_at IS NULL',(user['id'],)).fetchone()['n']
 return jsonify(enabled=bool(row and row['enabled_at']),recovery_remaining=unused)

@bp.post('/api/account/2fa/setup')
def setup():
 user=get_user();data=payload()
 if not allow_attempt('two-factor-settings',12) or not valid_password(user,data):return jsonify(error='Comprueba tu contraseña y espera si has hecho varios intentos.'),403
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');old=conn.execute('SELECT enabled_at FROM member_two_factor WHERE member_id=?',(user['id'],)).fetchone()
  if old and old['enabled_at']:return jsonify(error='La verificación en dos pasos ya está activa.'),409
  nonce=secrets.token_hex(24)
  conn.execute('INSERT INTO member_two_factor(member_id,pending_nonce,pending_until) VALUES(?,?,?) ON CONFLICT(member_id) DO UPDATE SET pending_nonce=excluded.pending_nonce,pending_until=excluded.pending_until',(user['id'],nonce,stamp(now_utc()+timedelta(minutes=10))))
 secret=base64.b32encode(key_for(user['id'],nonce)).decode().rstrip('=')
 uri='otpauth://totp/'+quote('electronicama del bueno:'+user['username'],safe='')+'?'+urlencode(dict(secret=secret,issuer='electronicama del bueno',algorithm='SHA1',digits=6,period=30))
 return jsonify(secret=secret,provisioning_uri=uri,expires_seconds=600)

@bp.post('/api/account/2fa/enable')
def enable():
 user=get_user();data=payload()
 if not user or not allow_attempt('two-factor-enable',12):return jsonify(error='Entra en tu cuenta o espera antes de volver a intentarlo.'),403
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM member_two_factor WHERE member_id=?',(user['id'],)).fetchone()
  if not row or row['enabled_at'] or not row['pending_nonce'] or row['pending_until']<=stamp(now_utc()):return jsonify(error='Vuelve a preparar la verificación; la configuración pendiente caduca a los diez minutos.'),409
  counter=matching_counter(user['id'],row['pending_nonce'],data.get('otp',''))
  if counter is None:return jsonify(error='El código de la app autenticadora no coincide.'),400
  conn.execute('UPDATE member_two_factor SET nonce=pending_nonce,enabled_at=?,key_id=?,last_counter=?,pending_nonce=NULL,pending_until=NULL WHERE member_id=?',(stamp(now_utc()),key_id(),counter,user['id']))
  conn.execute('DELETE FROM two_factor_recovery WHERE member_id=?',(user['id'],))
  codes=[]
  for _ in range(8):
   raw=secrets.token_hex(10).upper();code='-'.join(raw[i:i+4] for i in range(0,20,4));codes.append(code)
   conn.execute('INSERT INTO two_factor_recovery(member_id,code_hash) VALUES(?,?)',(user['id'],recovery_hash(user['id'],code)))
  conn.execute('UPDATE members SET session_version=session_version+1 WHERE id=?',(user['id'],))
  version=conn.execute('SELECT session_version FROM members WHERE id=?',(user['id'],)).fetchone()['session_version']
 session['session_version']=version
 return jsonify(ok=True,recovery_codes=codes,other_sessions_closed=True)

@bp.post('/api/account/2fa/disable')
def disable():
 user=get_user();data=payload()
 if not allow_attempt('two-factor-settings',12) or not valid_password(user,data):return jsonify(error='Comprueba tu contraseña y espera si has hecho varios intentos.'),403
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT enabled_at FROM member_two_factor WHERE member_id=?',(user['id'],)).fetchone()
  if not row or not row['enabled_at']:return jsonify(error='La verificación en dos pasos no está activa.'),409
  if not consume(conn,user,data):return jsonify(error='Introduce un código nuevo de la app o un código de recuperación sin usar.'),403
  conn.execute('DELETE FROM two_factor_recovery WHERE member_id=?',(user['id'],))
  conn.execute('DELETE FROM member_two_factor WHERE member_id=?',(user['id'],))
  conn.execute('UPDATE members SET session_version=session_version+1 WHERE id=?',(user['id'],))
  version=conn.execute('SELECT session_version FROM members WHERE id=?',(user['id'],)).fetchone()['session_version']
 session['session_version']=version
 return jsonify(ok=True,other_sessions_closed=True)

def install(app):app.register_blueprint(bp)
