"""Community videos: direct multipart uploads stay private until manual review."""
from __future__ import annotations

from datetime import timedelta
from functools import wraps
import math
import re
import secrets

from flask import Blueprint, jsonify, redirect, request

from membership import database, get_user, now_utc, payload, require_admin, stamp
from moderation import validate_public_text
from storage import PostgresConnection
import video_storage as storage


bp = Blueprint('videos', __name__)
CATEGORIES = {'music', 'dance', 'ai', 'other'}
MIME_EXTENSIONS = {'video/mp4': 'mp4', 'video/quicktime': 'mov', 'video/webm': 'webm'}
STATES = {'uploading', 'quarantined', 'published', 'rejected', 'failed', 'deleted'}
PAGE_SIZE = 20
ACTIVE_OWNER = "NOT EXISTS(SELECT 1 FROM member_archives a WHERE a.member_id=v.owner_id AND a.restored_at IS NULL)"
BASE_SELECT = '''SELECT v.*,m.username,p.nickname,
    (SELECT COUNT(*) FROM community_video_reports r WHERE r.video_id=v.id) AS report_count
    FROM community_videos v JOIN members m ON m.id=v.owner_id
    LEFT JOIN member_profiles p ON p.member_id=m.id'''


def init_database():
    with database() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS community_videos (
          id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES members(id),
          title TEXT NOT NULL,description TEXT NOT NULL,category TEXT NOT NULL,
          filename TEXT NOT NULL,mime_type TEXT NOT NULL,size_bytes BIGINT NOT NULL,
          object_key TEXT NOT NULL UNIQUE,upload_id TEXT,
          part_size BIGINT NOT NULL,part_count INTEGER NOT NULL,
          state TEXT NOT NULL,technical_checked INTEGER NOT NULL DEFAULT 0,
          verified_etag TEXT,storage_completed_at TEXT,
          operation_token TEXT,operation_expires_at TEXT,
          review_reason TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,updated_at TEXT NOT NULL,published_at TEXT,
          revision INTEGER NOT NULL DEFAULT 0,storage_deleted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS community_videos_owner ON community_videos(owner_id,created_at);
        CREATE INDEX IF NOT EXISTS community_videos_state ON community_videos(state,created_at);
        CREATE TABLE IF NOT EXISTS community_video_reviews (
          id TEXT PRIMARY KEY,video_id TEXT NOT NULL REFERENCES community_videos(id),
          actor_id TEXT NOT NULL REFERENCES members(id),previous_state TEXT NOT NULL,
          new_state TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS community_video_reviews_video ON community_video_reviews(video_id,created_at);
        CREATE TABLE IF NOT EXISTS community_video_reports (
          id TEXT PRIMARY KEY,video_id TEXT NOT NULL REFERENCES community_videos(id),
          reporter_id TEXT NOT NULL REFERENCES members(id),reason TEXT NOT NULL,
          created_at TEXT NOT NULL,UNIQUE(video_id,reporter_id)
        );
        CREATE INDEX IF NOT EXISTS community_video_reports_video ON community_video_reports(video_id,created_at);
        CREATE INDEX IF NOT EXISTS community_video_reports_reporter ON community_video_reports(reporter_id,created_at);
        ''')
        # Idempotent for a development database opened during feature rollout.
        if isinstance(conn, PostgresConnection):
            columns = {row['column_name'] for row in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='maggy' AND table_name='community_videos'").fetchall()}
        else:
            columns = {row['name'] for row in conn.execute('PRAGMA table_info(community_videos)').fetchall()}
        for name, declaration in [('revision', 'INTEGER NOT NULL DEFAULT 0'), ('storage_deleted_at', 'TEXT')]:
            if name not in columns:
                conn.execute('ALTER TABLE community_videos ADD COLUMN ' + name + ' ' + declaration)


def member_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not get_user():
            return jsonify(error='Inicia sesión con una cuenta gratuita para compartir vídeos.', code='login_required'), 401
        return fn(*args, **kwargs)
    return wrapped


def error(message, status=400, code=None):
    return jsonify(error=message, **({'code': code} if code else {})), status


def clean_text(value, maximum, label, required=False):
    if not isinstance(value, str):
        raise ValueError(label + ' debe ser texto.')
    value = value.strip()
    if len(value) > maximum or required and not value:
        raise ValueError(label + ' no tiene una longitud válida.')
    if any(ord(char) < 32 and char not in '\n\r\t' for char in value):
        raise ValueError(label + ' contiene caracteres no válidos.')
    return value


def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(label + ' debe ser un número entero.')
    return value


def page_number():
    value = request.args.get('page', '1')
    if not re.fullmatch(r'[1-9][0-9]{0,8}', value):
        raise ValueError('Selecciona una página válida.')
    return int(value)


def find_video(conn, ident):
    if not re.fullmatch(r'[a-f0-9]{32}', str(ident)):
        return None
    return conn.execute(BASE_SELECT + ' WHERE v.id=?', (ident,)).fetchone()


def owner_active(conn, owner_id):
    return conn.execute('''SELECT 1 FROM members m WHERE m.id=? AND NOT EXISTS(
        SELECT 1 FROM member_archives a WHERE a.member_id=m.id AND a.restored_at IS NULL)''', (owner_id,)).fetchone() is not None


def public_video(row, private=False, admin=False):
    item = {key: row[key] for key in ('id', 'title', 'description', 'category', 'size_bytes', 'mime_type', 'state', 'created_at', 'published_at')}
    item['author'] = {'username': row['username'], 'nickname': row['nickname'] or row['username']}
    if private:
        item.update(technical_checked=bool(row['technical_checked']), review_reason=row['review_reason'], updated_at=row['updated_at'],
                    storage_cleanup_pending=row['state'] == 'deleted' and not row['storage_deleted_at'])
    if admin:
        item['report_count'] = row['report_count']
    return item


def listing(where, parameters, private=False, admin=False):
    page = page_number()
    with database() as conn:
        total = conn.execute('SELECT COUNT(*) AS n FROM community_videos v WHERE ' + where, parameters).fetchone()['n']
        rows = conn.execute(BASE_SELECT + ' WHERE ' + where + ' ORDER BY v.created_at DESC,v.id DESC LIMIT ? OFFSET ?',
                            tuple(parameters) + (PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
    return jsonify(videos=[public_video(row, private, admin) for row in rows], total=total, page=page, pages=max(1, math.ceil(total / PAGE_SIZE)))


def audit(conn, row, actor, new_state, reason):
    conn.execute('INSERT INTO community_video_reviews VALUES(?,?,?,?,?,?,?)',
                 (secrets.token_hex(16), row['id'], actor, row['state'], new_state, reason, stamp(now_utc())))


def storage_unavailable():
    return error('La subida de vídeos se está preparando. Inténtalo más adelante.', 503, 'storage_unavailable')


@bp.get('/api/videos/config')
def configuration():
    info = storage.configuration()
    return jsonify(storage_ready=bool(info.get('storage_ready', storage.ready())),
                   max_file_bytes=info['max_file_bytes'], allowed_mime_types=list(MIME_EXTENSIONS))


@bp.get('/api/videos')
def catalogue():
    category = request.args.get('category', 'all')
    if category not in CATEGORIES | {'all'}:
        return error('Selecciona una categoría válida.')
    try:
        query = clean_text(request.args.get('q', ''), 120, 'La búsqueda')
        where = "v.state='published' AND " + ACTIVE_OWNER
        parameters = []
        if category != 'all':
            where += ' AND v.category=?'; parameters.append(category)
        if query:
            where += ' AND (LOWER(v.title) LIKE ? OR LOWER(v.description) LIKE ?)'
            parameters.extend(['%' + query.lower() + '%'] * 2)
        return listing(where, parameters)
    except ValueError as exc:
        return error(str(exc))


@bp.get('/api/videos/me')
@member_required
def mine():
    try:
        return listing("v.owner_id=? AND (v.state!='deleted' OR v.storage_deleted_at IS NULL)", [get_user()['id']], private=True)
    except ValueError as exc:
        return error(str(exc))


@bp.post('/api/videos/uploads')
@member_required
def begin_upload():
    if not storage.ready():
        return storage_unavailable()
    data = payload()
    try:
        title = clean_text(data.get('title'), 160, 'El título', True)
        description = clean_text(data.get('description', ''), 3000, 'La descripción')
        validate_public_text(title + '\n' + description)
        category = data.get('category')
        if category not in CATEGORIES:
            raise ValueError('Selecciona una categoría válida.')
        filename = clean_text(data.get('filename', ''), 200, 'El nombre del archivo', True)
        filename = filename.replace('\\', '/').rsplit('/', 1)[-1]
        mime = data.get('mime_type', '')
        if not mime:
            extension = filename.rsplit('.', 1)[-1].lower()
            mime = next((name for name, suffix in MIME_EXTENSIONS.items() if suffix == extension), '')
        if mime not in MIME_EXTENSIONS:
            raise ValueError('Usa un vídeo MP4, MOV o WebM.')
        size = integer(data.get('size_bytes'), 'El tamaño')
        if size <= 0:
            raise ValueError('Selecciona un vídeo que no esté vacío.')
        if size > storage.configuration()['max_file_bytes']:
            return error('El vídeo supera el tamaño técnico admitido por el almacenamiento.', 413, 'file_too_large')
        if data.get('rights_confirmed') is not True:
            raise ValueError('Confirma que puedes compartir el vídeo y que respetas la privacidad de las personas que aparecen.')
        plan = storage.multipart_plan(size)
    except (ValueError, TypeError) as exc:
        return error(str(exc))
    user = get_user(); ident = secrets.token_hex(16); instant = stamp(now_utc())
    key = 'videos/' + user['id'] + '/' + ident + '/original.' + MIME_EXTENSIONS[mime]
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        recent = conn.execute('SELECT COUNT(*) AS n FROM community_videos WHERE owner_id=? AND created_at>?',
                              (user['id'], stamp(now_utc() - timedelta(minutes=1)))).fetchone()['n']
        if recent >= 6:
            return error('Espera un minuto antes de iniciar otra subida.', 429, 'upload_rate_limited')
        conn.execute('''INSERT INTO community_videos(id,owner_id,title,description,category,filename,mime_type,size_bytes,
            object_key,part_size,part_count,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,'uploading',?,?)''',
                     (ident, user['id'], title, description, category, filename, mime, size, key,
                      plan['part_size'], plan['part_count'], instant, instant))
    try:
        upload_id = storage.start(key, mime)
        if not upload_id:
            raise RuntimeError('missing_upload_id')
    except Exception:
        with database() as conn:
            conn.execute("UPDATE community_videos SET state='failed',review_reason=?,updated_at=?,revision=revision+1 WHERE id=? AND state='uploading'",
                         ('No se pudo iniciar la subida.', stamp(now_utc()), ident))
        return error('No se pudo iniciar la subida. Vuelve a intentarlo.', 503, 'upload_start_failed')
    try:
        with database() as conn:
            result = conn.execute("UPDATE community_videos SET upload_id=?,updated_at=?,revision=revision+1 WHERE id=? AND state='uploading'",
                                  (upload_id, stamp(now_utc()), ident))
            stored = result.rowcount == 1
    except Exception:
        try: storage.abort(key, upload_id)
        except Exception: pass
        return error('No se pudo confirmar el inicio de la subida. El vídeo sigue privado.', 503, 'upload_start_unconfirmed')
    if not stored:
        # A cancellation may have arrived while R2 was starting the upload.
        # Preserve its now-known identifier so a failed abort can be retried.
        with database() as conn:
            conn.execute("UPDATE community_videos SET upload_id=?,storage_deleted_at=NULL,revision=revision+1 WHERE id=? AND state='deleted'", (upload_id, ident))
        try:
            storage.abort(key, upload_id)
        except Exception:
            pass
        else:
            with database() as conn:
                conn.execute("UPDATE community_videos SET storage_deleted_at=?,revision=revision+1 WHERE id=? AND state='deleted'", (stamp(now_utc()), ident))
        return error('La subida ya no está disponible.', 409)
    return jsonify(id=ident, part_size=plan['part_size'], part_count=plan['part_count']), 201


@bp.post('/api/videos/uploads/<ident>/parts')
@member_required
def upload_part(ident):
    try:
        number = integer(payload().get('part_number'), 'La parte')
    except ValueError as exc:
        return error(str(exc))
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = find_video(conn, ident)
        if row and row['owner_id'] == get_user()['id'] and row['operation_token'] and row['operation_expires_at'] <= stamp(now_utc()):
            conn.execute('UPDATE community_videos SET operation_token=NULL,operation_expires_at=NULL,revision=revision+1 WHERE id=?', (ident,))
            row = find_video(conn, ident)
    if not row or row['owner_id'] != get_user()['id']:
        return error('Subida no encontrada.', 404)
    if row['state'] != 'uploading' or not row['upload_id'] or row['storage_completed_at']:
        return error('La subida ya no admite más partes.', 409)
    if row['operation_token'] and row['operation_expires_at'] > stamp(now_utc()):
        return error('Se está comprobando el vídeo. Espera unos instantes.', 409)
    if not 1 <= number <= row['part_count']:
        return error('La parte no pertenece a este vídeo.')
    if not storage.ready():
        return storage_unavailable()
    try:
        url = storage.presign_part(row['object_key'], row['upload_id'], number)
    except Exception:
        return error('No se pudo preparar esta parte. Inténtalo de nuevo.', 503)
    # A concurrent cancellation prevents issuing a fresh URL after this point.
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        current = find_video(conn, ident)
        busy = current and current['operation_token'] and current['operation_expires_at'] > stamp(now_utc())
        if not current or current['state'] != 'uploading' or current['storage_completed_at'] or busy or not owner_active(conn, current['owner_id']):
            return error('La subida ya no está disponible.', 409)
    return jsonify(url=url, part_number=number, expires_in=600)


def actual_parts(row, parts):
    if not isinstance(parts, list) or len(parts) != row['part_count']:
        raise ValueError('La subida todavía no contiene todas las partes.')
    by_number = {}
    for part in parts:
        number, size, etag = part.get('PartNumber'), part.get('Size'), part.get('ETag')
        if isinstance(number, bool) or not isinstance(number, int) or number in by_number:
            raise ValueError('Las partes del vídeo no son válidas.')
        expected = min(row['part_size'], row['size_bytes'] - (number - 1) * row['part_size'])
        if not 1 <= number <= row['part_count'] or isinstance(size, bool) or size != expected or not isinstance(etag, str) or not etag:
            raise ValueError('El tamaño de una parte no coincide con el vídeo.')
        by_number[number] = {'PartNumber': number, 'ETag': etag}
    return [by_number[number] for number in range(1, row['part_count'] + 1)]


def valid_metadata(row, metadata):
    return (metadata.get('ContentLength') == row['size_bytes'] and
            str(metadata.get('ContentType', '')).split(';', 1)[0].strip().lower() == row['mime_type'])


def unlock(ident, token):
    with database() as conn:
        conn.execute('UPDATE community_videos SET operation_token=NULL,operation_expires_at=NULL,revision=revision+1 WHERE id=? AND operation_token=?', (ident, token))


@bp.post('/api/videos/uploads/<ident>/complete')
@member_required
def complete_upload(ident):
    if not storage.ready():
        return storage_unavailable()
    token = secrets.token_hex(16)
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = find_video(conn, ident)
        if not row or row['owner_id'] != get_user()['id']:
            return error('Subida no encontrada.', 404)
        if row['state'] in {'quarantined', 'published'}:
            return jsonify(ok=True, video=public_video(row, private=True))
        if row['state'] != 'uploading' or not row['upload_id']:
            return error('Esta subida ya no se puede completar.', 409)
        if row['operation_token'] and row['operation_expires_at'] > stamp(now_utc()):
            return error('Se está comprobando el vídeo. Espera unos instantes.', 409)
        conn.execute('UPDATE community_videos SET operation_token=?,operation_expires_at=?,revision=revision+1 WHERE id=?',
                     (token, stamp(now_utc() + timedelta(minutes=5)), ident))
    try:
        metadata = None
        if not row['storage_completed_at']:
            try:
                parts = storage.list_parts(row['object_key'], row['upload_id'])
            except Exception:
                # A previous remote completion can have succeeded before a lost
                # response. Recover only from the actual object, never client claims.
                metadata = storage.head(row['object_key'])
                if not valid_metadata(row, metadata):
                    raise ValueError('El archivo guardado no coincide con el vídeo anunciado.')
            else:
                verified_parts = actual_parts(row, parts)
                storage.complete(row['object_key'], row['upload_id'], verified_parts)
            with database() as conn:
                stored = conn.execute('UPDATE community_videos SET storage_completed_at=?,revision=revision+1 WHERE id=? AND state=\'uploading\' AND operation_token=?',
                                      (stamp(now_utc()), ident, token)).rowcount == 1
            if not stored:
                # A remote completion can finish after a cancellation's first
                # cleanup. Reopen the cleanup marker before touching its new
                # object; never remove an object accepted by a newer lease.
                with database() as conn:
                    current = find_video(conn, ident)
                    cancelled = current and current['state'] == 'deleted'
                    if cancelled:
                        conn.execute("UPDATE community_videos SET storage_completed_at=?,storage_deleted_at=NULL,revision=revision+1 WHERE id=? AND state='deleted'", (stamp(now_utc()), ident))
                if cancelled:
                    try:
                        storage.delete(row['object_key'])
                    except Exception:
                        pass
                    else:
                        with database() as conn:
                            conn.execute("UPDATE community_videos SET storage_deleted_at=?,revision=revision+1 WHERE id=? AND state='deleted'", (stamp(now_utc()), ident))
                return error('La subida fue retirada durante la comprobación.', 409)
        metadata = metadata or storage.head(row['object_key'])
        if not valid_metadata(row, metadata) or not storage.sniff_video(storage.sample(row['object_key'], limit=4096), row['mime_type']):
            raise ValueError('El archivo recibido no es un vídeo válido del formato anunciado.')
        etag = str(metadata.get('ETag', '')).strip('"')
        if not etag:
            raise RuntimeError('missing_object_etag')
    except ValueError as exc:
        # Incomplete parts are recoverable; a finalized non-video is rejected.
        with database() as conn:
            current = find_video(conn, ident)
            finalized = current and bool(current['storage_completed_at'])
            conn.execute('''UPDATE community_videos SET state=?,review_reason=?,technical_checked=0,
                operation_token=NULL,operation_expires_at=NULL,updated_at=?,revision=revision+1 WHERE id=? AND state='uploading' AND operation_token=?''',
                         ('rejected' if finalized else 'uploading', str(exc) if finalized else '', stamp(now_utc()), ident, token))
        return error(str(exc), 422 if finalized else 409, 'invalid_video' if finalized else 'incomplete_upload')
    except Exception:
        unlock(ident, token)
        return error('No se pudo comprobar la subida. El vídeo sigue privado y puedes volver a intentarlo.', 503, 'upload_check_failed')
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        current = find_video(conn, ident)
        if not current or current['state'] != 'uploading' or current['operation_token'] != token or not owner_active(conn, current['owner_id']):
            if current and current['operation_token'] == token:
                conn.execute('UPDATE community_videos SET operation_token=NULL,operation_expires_at=NULL,revision=revision+1 WHERE id=?', (ident,))
            return error('La cuenta o la subida ya no están disponibles.', 409)
        conn.execute('''UPDATE community_videos SET state='quarantined',technical_checked=1,verified_etag=?,
            operation_token=NULL,operation_expires_at=NULL,review_reason='',updated_at=?,revision=revision+1 WHERE id=? AND operation_token=?''',
                     (etag, stamp(now_utc()), ident, token))
        current = find_video(conn, ident)
    return jsonify(ok=True, video=public_video(current, private=True))


@bp.post('/api/videos/<ident>/delete')
@member_required
def delete_video(ident):
    user = get_user()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = find_video(conn, ident)
        if not row or row['owner_id'] != user['id'] and user['role'] != 'admin':
            return error('Vídeo no encontrado.', 404)
        if row['state'] != 'deleted':
            audit(conn, row, user['id'], 'deleted', 'Vídeo retirado por su autor.' if row['owner_id'] == user['id'] else 'Vídeo retirado por administración.')
            conn.execute("UPDATE community_videos SET state='deleted',operation_token=NULL,operation_expires_at=NULL,updated_at=?,revision=revision+1 WHERE id=?", (stamp(now_utc()), ident))
        cleanup_revision = row['revision'] + (row['state'] != 'deleted')
    deleted = False
    if storage.ready():
        # Without an upload identifier a lost start response is uncertain;
        # an ordinary object DELETE cannot prove multipart fragments are gone.
        aborted = bool(row['upload_id'] or row['storage_completed_at'])
        if row['upload_id'] and not row['storage_completed_at']:
            try: storage.abort(row['object_key'], row['upload_id'])
            except Exception as exc:
                details = getattr(exc, 'response', {})
                aborted = isinstance(details, dict) and details.get('Error', {}).get('Code') in {'NoSuchUpload', 'NoSuchKey', '404', 'NotFound'}
        try:
            storage.delete(row['object_key']); deleted = aborted
        except Exception:
            pass
    if deleted:
        with database() as conn:
            # A late completion can reopen cleanup while the remote DELETE is
            # in flight. Do not overwrite its newer pending marker.
            conn.execute("UPDATE community_videos SET storage_deleted_at=?,revision=revision+1 WHERE id=? AND state='deleted' AND revision=?",
                         (stamp(now_utc()), ident, cleanup_revision))
            current = find_video(conn, ident)
            deleted = bool(current and current['state'] == 'deleted' and current['storage_deleted_at'])
    return jsonify(ok=True, storage_deleted=deleted)


def media_redirect(ident, private=False):
    with database() as conn:
        row = find_video(conn, ident)
        active = row is not None and owner_active(conn, row['owner_id'])
    allowed = row and row['technical_checked'] and (row['state'] in {'quarantined', 'published', 'rejected'} if private else row['state'] == 'published')
    if not allowed or not active:
        return error('Vídeo no disponible.', 404)
    if not storage.ready():
        return error('El vídeo no está disponible temporalmente. Inténtalo más tarde.', 503)
    try:
        url = storage.playback_url(row['object_key'], row['mime_type'], 'video-' + row['id'] + '.' + MIME_EXTENSIONS[row['mime_type']])
    except Exception:
        return error('No se pudo abrir el vídeo. Inténtalo más tarde.', 503)
    with database() as conn:
        current = find_video(conn, ident)
        if not current or not owner_active(conn, current['owner_id']) or not current['technical_checked'] or (current['state'] not in {'quarantined', 'published', 'rejected'} if private else current['state'] != 'published'):
            return error('Vídeo no disponible.', 404)
    response = redirect(url, code=302)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.get('/api/videos/<ident>/play')
def play(ident):
    return media_redirect(ident)


@bp.get('/api/admin/videos')
@require_admin
def admin_catalogue():
    state = request.args.get('state', 'quarantined')
    if state not in STATES | {'all'}:
        return error('Selecciona un estado válido.')
    try:
        return listing('1=1' if state == 'all' else 'v.state=?', [] if state == 'all' else [state], private=True, admin=True)
    except ValueError as exc:
        return error(str(exc))


@bp.get('/api/admin/videos/<ident>/preview')
@require_admin
def preview(ident):
    return media_redirect(ident, private=True)


@bp.post('/api/admin/videos/<ident>/review')
@require_admin
def review(ident):
    data = payload(); decision = data.get('decision')
    if not isinstance(decision, str) or decision not in {'approve', 'reject', 'quarantine'}:
        return error('Selecciona una decisión válida.')
    try:
        reason = clean_text(data.get('reason', ''), 1000, 'El motivo', decision != 'approve')
    except ValueError as exc:
        return error(str(exc))
    if decision == 'approve' and data.get('review_confirmed') is not True:
        return error('Confirma que has revisado el vídeo antes de publicarlo.')
    with database() as conn:
        row = find_video(conn, ident)
        active_owner = row and owner_active(conn, row['owner_id'])
    if not row or row['state'] in {'uploading', 'failed', 'deleted'}:
        return error('El vídeo no está listo para revisión.', 409)
    if not active_owner:
        return error('La cuenta del autor no está disponible.', 409)
    if decision == 'approve':
        if row['state'] == 'published':
            return jsonify(ok=True, video=public_video(row, private=True, admin=True))
        if row['state'] != 'quarantined' or not row['technical_checked']:
            return error('Solo se puede publicar un vídeo válido que esté en cuarentena.', 409)
        if not storage.ready():
            return storage_unavailable()
        try:
            metadata = storage.head(row['object_key'])
            if not valid_metadata(row, metadata) or str(metadata.get('ETag', '')).strip('"') != row['verified_etag']:
                return error('El archivo ha cambiado o no coincide con el revisado. Mantén el vídeo en cuarentena.', 409)
        except Exception:
            return error('No se pudo confirmar el archivo. El vídeo sigue en cuarentena.', 503)
    new_state = {'approve': 'published', 'reject': 'rejected', 'quarantine': 'quarantined'}[decision]
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        current = find_video(conn, ident)
        if not current or current['state'] != row['state'] or current['revision'] != row['revision'] or not owner_active(conn, current['owner_id']):
            return error('El vídeo o la cuenta han cambiado. Actualiza la lista antes de decidir.', 409)
        if decision == 'approve' and (current['state'] != 'quarantined' or not current['technical_checked'] or current['verified_etag'] != row['verified_etag']):
            return error('El vídeo necesita otra revisión.', 409)
        audit(conn, current, get_user()['id'], new_state, reason)
        instant = stamp(now_utc())
        conn.execute('UPDATE community_videos SET state=?,review_reason=?,published_at=?,updated_at=?,revision=revision+1 WHERE id=?',
                     (new_state, reason, instant if new_state == 'published' else None, instant, ident))
        current = find_video(conn, ident)
    return jsonify(ok=True, video=public_video(current, private=True, admin=True))


@bp.post('/api/videos/<ident>/report')
@member_required
def report(ident):
    try:
        reason = clean_text(payload().get('reason'), 1000, 'El motivo', True)
    except ValueError as exc:
        return error(str(exc))
    user = get_user()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = find_video(conn, ident)
        if not row or row['state'] != 'published' or not owner_active(conn, row['owner_id']):
            return error('Vídeo no disponible.', 404)
        if conn.execute('SELECT 1 FROM community_video_reports WHERE video_id=? AND reporter_id=?', (ident, user['id'])).fetchone():
            return jsonify(ok=True)
        recent = conn.execute('SELECT COUNT(*) AS n FROM community_video_reports WHERE reporter_id=? AND created_at>?',
                              (user['id'], stamp(now_utc() - timedelta(minutes=1)))).fetchone()['n']
        if recent >= 10:
            return error('Espera un minuto antes de enviar otra denuncia.', 429)
        conn.execute('INSERT INTO community_video_reports VALUES(?,?,?,?,?)', (secrets.token_hex(16), ident, user['id'], reason, stamp(now_utc())))
    return jsonify(ok=True)


def install(app):
    app.register_blueprint(bp)
