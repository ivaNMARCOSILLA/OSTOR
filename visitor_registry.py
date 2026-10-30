"""Consent-based first-party visit registry. Browser/network estimates, not people IDs."""
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
from datetime import timedelta
from flask import Blueprint,current_app,jsonify,request
from itsdangerous import URLSafeTimedSerializer,BadSignature
from membership import database,get_user,now_utc,stamp,require_admin

bp=Blueprint('visitor_registry',__name__)
COOKIE='electronicama_visits'
RETENTION_DAYS=7
PAGES={'/','/live','/account','/legal/privacidad.html','/legal/cookies.html','/legal/aviso-legal.html'}


def init_database():
    with database() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS visitor_devices (
            id TEXT PRIMARY KEY,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS visitor_sessions (
            id TEXT PRIMARY KEY,device_id TEXT NOT NULL REFERENCES visitor_devices(id) ON DELETE CASCADE,
            member_id TEXT REFERENCES members(id) ON DELETE SET NULL,account_kind TEXT NOT NULL,
            started_at TEXT NOT NULL,last_seen TEXT NOT NULL,pageviews INTEGER NOT NULL DEFAULT 0,last_page TEXT NOT NULL,
            network_id TEXT,network_day TEXT NOT NULL,device TEXT NOT NULL,os TEXT NOT NULL,browser TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS visitor_session_recent ON visitor_sessions(last_seen,id);
        CREATE INDEX IF NOT EXISTS visitor_session_device ON visitor_sessions(device_id,last_seen);
        ''')


def cleanup(conn):
    cutoff=stamp(now_utc()-timedelta(days=RETENTION_DAYS))
    conn.execute('DELETE FROM visitor_sessions WHERE last_seen<?',(cutoff,))
    conn.execute('DELETE FROM visitor_devices WHERE last_seen<?',(cutoff,))


def signer():
    return URLSafeTimedSerializer(current_app.secret_key,salt='visitor-registry-v1')


def cookie_payload():
    try:
        data=signer().loads(request.cookies.get(COOKIE,''),max_age=30*86400)
        if isinstance(data,dict) and isinstance(data.get('device'),str) and re.fullmatch(r'[a-f0-9]{32}',data['device']) and isinstance(data.get('session'),str) and re.fullmatch(r'[a-f0-9]{32}',data['session']):return data
    except BadSignature:pass
    return None


def cookie_identity():
    data=cookie_payload()
    return data['device'] if data else None


def protected(value,purpose):
    key=current_app.secret_key
    if isinstance(key,str):key=key.encode()
    return hmac.new(key,(purpose+'|'+value).encode(),hashlib.sha256).hexdigest()


def address():
    # Vercel overwrites its own x-vercel-forwarded-for header at its edge. Generic
    # forwarded/x-real-ip headers are untrusted and are never consumed here.
    original=request.environ.get('werkzeug.proxy_fix.orig',{})
    value=request.headers.get('X-Vercel-Forwarded-For') if os.getenv('VERCEL')=='1' else original.get('REMOTE_ADDR',request.remote_addr)
    try:
        if not isinstance(value,str) or '%' in value:return None
        parsed=ipaddress.ip_address(value)
        parsed=getattr(parsed,'ipv4_mapped',None) or parsed
        if parsed.is_global:return parsed.compressed
    except ValueError:pass
    return None


def coarse_device():
    ua=request.headers.get('User-Agent','')[:1024].lower()
    if any(x in ua for x in ['bot','crawler','spider','headless']):device='Automatización declarada'
    elif 'ipad' in ua or 'tablet' in ua or ('android' in ua and 'mobile' not in ua):device='Tableta'
    elif 'mobile' in ua or 'iphone' in ua or 'ipod' in ua:device='Móvil'
    elif any(x in ua for x in ['windows','macintosh','linux','cros']):device='Ordenador'
    else:device='Desconocido'
    os_name='iOS' if any(x in ua for x in ['iphone','ipad','ipod']) else 'Android' if 'android' in ua else 'ChromeOS' if 'cros' in ua else 'Windows' if 'windows' in ua else 'macOS' if 'macintosh' in ua else 'Linux' if 'linux' in ua else 'Desconocido'
    browser='Edge' if 'edg/' in ua or 'edga/' in ua or 'edgios/' in ua else 'Opera' if 'opr/' in ua or 'opera' in ua else 'Firefox' if 'firefox/' in ua or 'fxios/' in ua else 'Chrome' if 'chrome/' in ua or 'crios/' in ua else 'Safari' if 'safari/' in ua else 'Desconocido'
    return device,os_name,browser


def erase_current():
    from analytics import forget_presence
    forget_presence()
    raw=cookie_identity()
    if raw:
        with database() as conn:conn.execute('DELETE FROM visitor_devices WHERE id=?',(protected(raw,'browser'),))


def private_response(data):
    response=jsonify(**data);response.headers['Cache-Control']='no-store';return response


@bp.post('/api/visits')
def record_visit():
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return private_response({'error':'Visita no válida.'}),400
    privacy=request.headers.get('Sec-GPC')=='1' or request.headers.get('DNT')=='1'
    if data.get('consent') is not True or privacy:
        erase_current();response=private_response({'recorded':False,'reason':'privacy_signal' if privacy else 'consent_required'});response.delete_cookie(COOKIE);response.delete_cookie('ol_presence');return response
    page=data.get('page');event=data.get('event','page');view=event=='page'
    if not isinstance(page,str) or not isinstance(event,str) or page not in PAGES or event not in {'page','heartbeat'}:return private_response({'error':'Página o tipo de visita no válido.'}),400
    cookie=cookie_payload();raw=cookie['device'] if cookie else secrets.token_hex(16);ident=protected(raw,'browser');instant=now_utc();at=stamp(instant);day=instant.date().isoformat()
    ip=address();network=protected(ip,'network-'+day) if ip else None
    user=get_user();member=user['id'] if user else None;kind='registered' if user else 'guest';device,os_name,browser=coarse_device()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE');cleanup(conn)
        # Rate buckets use a secret-key digest and cannot be changed by a username
        # supplied in the JSON body. No address or user agent is written to DB.
        bucket=protected(ident,'visit-rate')
        count=conn.execute('SELECT COUNT(*) AS n FROM login_attempts WHERE bucket=? AND attempted_at>?',(bucket,stamp(instant-timedelta(minutes=15)))).fetchone()['n']
        if count>=120:return private_response({'error':'Demasiadas actualizaciones de visitas. Espera un momento.'}),429
        conn.execute('INSERT INTO login_attempts(bucket,attempted_at) VALUES(?,?)',(bucket,at))
        conn.execute('DELETE FROM login_attempts WHERE attempted_at<?',(stamp(instant-timedelta(minutes=15)),))
        conn.execute('INSERT INTO visitor_devices(id,first_seen,last_seen) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen',(ident,at,at))
        previous=conn.execute('SELECT * FROM visitor_sessions WHERE id=? AND device_id=?',(cookie['session'],ident)).fetchone() if cookie else None
        continuing=bool(previous and previous['last_seen']>=stamp(instant-timedelta(minutes=30)) and previous['member_id']==member and previous['account_kind']==kind and previous['network_id']==network and previous['network_day']==day)
        if continuing:
            session_id=previous['id']
            conn.execute('UPDATE visitor_sessions SET last_seen=?,last_page=?,pageviews=pageviews+? WHERE id=?',(at,page,int(view),previous['id']))
        else:
            session_id=secrets.token_hex(16)
            conn.execute('INSERT INTO visitor_sessions(id,device_id,member_id,account_kind,started_at,last_seen,pageviews,last_page,network_id,network_day,device,os,browser) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(session_id,ident,member,kind,at,at,int(view),page,network,day,device,os_name,browser))
    response=private_response({'recorded':True})
    response.set_cookie(COOKIE,signer().dumps({'device':raw,'session':session_id}),max_age=30*86400,httponly=True,secure=current_app.config['SESSION_COOKIE_SECURE'],samesite='Lax')
    return response


@bp.post('/api/visits/consent')
def withdraw_consent():
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or data.get('allowed') is not False:return private_response({'error':'Elección no válida.'}),400
    erase_current();response=private_response({'ok':True});response.delete_cookie(COOKIE);response.delete_cookie('ol_presence');return response


@bp.get('/api/admin/visits')
@require_admin
def list_visits():
    try:page=max(1,min(int(request.args.get('page',1)),1000000))
    except ValueError:return private_response({'error':'Página no válida.'}),400
    kind=request.args.get('kind','all')
    if kind not in {'all','guest','registered'}:return private_response({'error':'Filtro no válido.'}),400
    where='' if kind=='all' else ' WHERE v.account_kind=?';args=() if kind=='all' else (kind,)
    with database() as conn:
        cleanup(conn)
        summary=conn.execute('SELECT COUNT(*) AS sessions,COUNT(DISTINCT device_id) AS browsers,COALESCE(SUM(CASE WHEN account_kind=\'registered\' THEN 1 ELSE 0 END),0) AS registered,COALESCE(SUM(CASE WHEN account_kind=\'guest\' THEN 1 ELSE 0 END),0) AS guests FROM visitor_sessions v'+where,args).fetchone()
        total=summary['sessions'];pages=max(1,(total+24)//25);page=min(page,pages)
        rows=conn.execute('SELECT v.*,m.username FROM visitor_sessions v LEFT JOIN members m ON m.id=v.member_id'+where+' ORDER BY v.last_seen DESC,v.id DESC LIMIT 25 OFFSET ?',(*args,25*(page-1))).fetchall()
    visits=[]
    for row in rows:
        item={key:row[key] for key in ['id','started_at','last_seen','pageviews','last_page','network_day','device','os','browser','username','account_kind']}
        item['device_id']=row['device_id'][:12];item['network_id']=row['network_id'][:12] if row['network_id'] else None
        item['label']=row['device']+' · '+row['os']+' · '+row['browser'];visits.append(item)
    return private_response({'visits':visits,'page':page,'pages':pages,'total':total,'retention_days':RETENTION_DAYS,'summary':dict(summary),'consented_only':True,'approximate':True})


@bp.get('/api/visits/public')
def public_visits():
    cutoff=stamp(now_utc()-timedelta(hours=24))
    with database() as conn:
        cleanup(conn)
        summary=conn.execute('SELECT COUNT(*) AS sessions,COUNT(DISTINCT device_id) AS browsers FROM visitor_sessions WHERE started_at>=?',(cutoff,)).fetchone()
        rows=conn.execute('SELECT started_at,device,last_page FROM visitor_sessions WHERE started_at>=? ORDER BY started_at DESC,id DESC LIMIT 20',(cutoff,)).fetchall()
    labels={'/':'Música','/live':'Ol Livis','/account':'Cuenta','/legal/privacidad.html':'Información legal','/legal/cookies.html':'Información legal','/legal/aviso-legal.html':'Información legal'}
    return private_response({'visits':[{'at':row['started_at'][:16]+':00+00:00','device':row['device'],'page':labels.get(row['last_page'],'Web')} for row in rows], 'summary':dict(summary),'window_hours':24,'limit':20,'consented_only':True,'approximate':True})


def install(app):
    app.register_blueprint(bp)
