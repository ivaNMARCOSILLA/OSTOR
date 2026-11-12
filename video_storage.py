"""Private multipart storage for community videos; no public object uploads.

Container sniffing below is a bounded format check, not an antivirus scan or a
content review. The video service keeps every completed upload in quarantine.
"""
import os
import re
from urllib.parse import urlsplit


MAX_FILE_BYTES = 5 * 1024 ** 4
MAX_PART_BYTES = 5 * 1024 ** 3
MIN_PART_BYTES = 8 * 1024 ** 2
MAX_PARTS = 10000
PART_URL_SECONDS = 600
PLAYBACK_URL_SECONDS = 60
ALLOWED_MIME_TYPES = ('video/mp4', 'video/webm', 'video/quicktime')
_MIME_EXTENSIONS = {'video/mp4': 'mp4', 'video/webm': 'webm', 'video/quicktime': 'mov'}


def _settings():
    def setting(name):
        return (os.getenv('VIDEO_' + name, '').strip() or os.getenv(name, '').strip())
    return {name: setting(name) for name in (
        'R2_ENDPOINT', 'R2_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY')}


def _endpoint(value):
    if not value or any(char.isspace() or ord(char) < 32 for char in value) or '?' in value or '#' in value:
        return ''
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ''
        labels = hostname.split('.')
        valid = (parsed.scheme == 'https' and parsed.username is None and parsed.password is None
                 and parsed.port in (None, 443) and parsed.path in ('', '/')
                 and hostname.endswith('.r2.cloudflarestorage.com')
                 and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels))
        return 'https://' + hostname if valid else ''
    except ValueError:
        return ''


def _size_limit():
    value = os.getenv('VIDEO_MAX_BYTES', '').strip()
    if not value:
        return MAX_FILE_BYTES, True
    if not re.fullmatch(r'[0-9]{1,20}', value):
        return MAX_FILE_BYTES, False
    amount = int(value)
    return (min(amount, MAX_FILE_BYTES), True) if amount > 0 else (MAX_FILE_BYTES, False)


def configuration():
    settings = _settings()
    bucket = settings['R2_BUCKET']
    configured = bool(_endpoint(settings['R2_ENDPOINT'])
                      and re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', bucket)
                      and settings['R2_ACCESS_KEY_ID'] and settings['R2_SECRET_ACCESS_KEY'])
    maximum, limit_valid = _size_limit()
    enabled = os.getenv('OL_VIDEOS_ENABLED') == '1'
    private_confirmed = os.getenv('VIDEO_STORAGE_PRIVATE_CONFIRMED') == '1'
    return {'enabled': enabled, 'storage_configured': configured,
            'private_confirmed': private_confirmed, 'size_limit_valid': limit_valid,
            'storage_ready': enabled and configured and private_confirmed and limit_valid,
            'max_file_bytes': maximum, 'allowed_mime_types': list(ALLOWED_MIME_TYPES)}


def ready():
    return configuration()['storage_ready']


def client():
    if not ready():
        raise RuntimeError('video_storage_not_ready')
    import boto3
    from botocore.config import Config
    settings = _settings()
    return boto3.client('s3', endpoint_url=_endpoint(settings['R2_ENDPOINT']),
                        aws_access_key_id=settings['R2_ACCESS_KEY_ID'],
                        aws_secret_access_key=settings['R2_SECRET_ACCESS_KEY'], region_name='auto',
                        config=Config(signature_version='s3v4', connect_timeout=3, read_timeout=10,
                                      retries={'max_attempts': 1}, s3={'addressing_style': 'path'}))


def multipart_plan(size):
    maximum, valid = _size_limit()
    if not valid:
        raise ValueError('video_storage_limit_invalid')
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= maximum:
        raise ValueError('video_size_invalid')
    mib = 1024 ** 2
    part_size = max(MIN_PART_BYTES, ((size + MAX_PARTS * mib - 1) // (MAX_PARTS * mib)) * mib)
    part_count = (size + part_size - 1) // part_size
    if part_size > MAX_PART_BYTES or part_count > MAX_PARTS:
        raise ValueError('video_size_invalid')
    return {'part_size': part_size, 'part_count': part_count}


def _key(value):
    if (not isinstance(value, str) or not re.fullmatch(r'videos/[A-Za-z0-9][A-Za-z0-9/_.-]{0,500}', value)
            or value.endswith('/') or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('video_object_key_invalid')
    return value


def _upload_id(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 2048
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError('video_upload_id_invalid')
    return value


def _part_number(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_PARTS:
        raise ValueError('video_part_number_invalid')
    return value


def _etag(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError('video_part_etag_invalid')
    return value


def _mime(value):
    if not isinstance(value, str):
        raise ValueError('video_mime_invalid')
    mime = value.split(';', 1)[0].strip().lower()
    if mime not in ALLOWED_MIME_TYPES:
        raise ValueError('video_mime_invalid')
    return mime


def _object_params(key):
    return {'Bucket': _settings()['R2_BUCKET'], 'Key': _key(key)}


def _signed_url(value):
    if not isinstance(value, str):
        raise RuntimeError('video_storage_signature_invalid')
    try:
        parsed = urlsplit(value)
        expected = urlsplit(_endpoint(_settings()['R2_ENDPOINT']))
        if (parsed.scheme != 'https' or parsed.hostname != expected.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.fragment):
            raise ValueError
    except ValueError:
        raise RuntimeError('video_storage_signature_invalid') from None
    return value


def start(key, mime):
    params = _object_params(key)
    result = client().create_multipart_upload(**params, ContentType=_mime(mime),
                                               CacheControl='private, no-store',
                                               Metadata={'upload-purpose': 'community-video'})
    return _upload_id(result.get('UploadId'))


def presign_part(key, upload_id, part_number):
    params = _object_params(key) | {'UploadId': _upload_id(upload_id),
                                    'PartNumber': _part_number(part_number)}
    return _signed_url(client().generate_presigned_url('upload_part', Params=params,
                                                       ExpiresIn=PART_URL_SECONDS, HttpMethod='PUT'))


def list_parts(key, upload_id):
    params = _object_params(key) | {'UploadId': _upload_id(upload_id), 'MaxParts': 1000}
    storage = client()
    collected = {}
    marker = 0
    for _ in range(MAX_PARTS + 1):
        response = storage.list_parts(**params, **({'PartNumberMarker': marker} if marker else {}))
        for part in response.get('Parts', []):
            number = _part_number(part.get('PartNumber'))
            size = part.get('Size')
            if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_PART_BYTES or number in collected:
                raise RuntimeError('video_storage_parts_invalid')
            collected[number] = {'PartNumber': number, 'ETag': _etag(part.get('ETag')), 'Size': size}
        if not response.get('IsTruncated'):
            return [collected[number] for number in sorted(collected)]
        next_marker = response.get('NextPartNumberMarker')
        if (isinstance(next_marker, bool) or not isinstance(next_marker, int)
                or not marker < next_marker <= MAX_PARTS):
            raise RuntimeError('video_storage_pagination_invalid')
        marker = next_marker
    raise RuntimeError('video_storage_pagination_invalid')


def complete(key, upload_id, parts):
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_PARTS:
        raise ValueError('video_parts_invalid')
    normalized = []
    for expected, part in enumerate(parts, 1):
        if not isinstance(part, dict) or _part_number(part.get('PartNumber')) != expected:
            raise ValueError('video_parts_invalid')
        normalized.append({'PartNumber': expected, 'ETag': _etag(part.get('ETag'))})
    params = _object_params(key) | {'UploadId': _upload_id(upload_id)}
    return _etag(client().complete_multipart_upload(**params, MultipartUpload={'Parts': normalized}).get('ETag'))


def abort(key, upload_id):
    client().abort_multipart_upload(**(_object_params(key) | {'UploadId': _upload_id(upload_id)}))


def delete(key):
    client().delete_object(**_object_params(key))


def head(key):
    response = client().head_object(**_object_params(key))
    return {'ContentLength': response.get('ContentLength'),
            'ContentType': str(response.get('ContentType', '')).split(';', 1)[0].strip().lower(),
            'ETag': response.get('ETag', '')}


def sample(key, limit=4096):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 65536:
        raise ValueError('video_sample_limit_invalid')
    response = client().get_object(**_object_params(key), Range=f'bytes=0-{limit - 1}')
    body = response.get('Body')
    if not body or not callable(getattr(body, 'read', None)):
        raise RuntimeError('video_storage_sample_invalid')
    try:
        data = body.read(limit)
        if not isinstance(data, bytes):
            raise RuntimeError('video_storage_sample_invalid')
        return data[:limit]
    finally:
        close = getattr(body, 'close', None)
        if callable(close):
            close()


def _filename(value, mime):
    stem = str(value or '').replace('\\', '/').rsplit('/', 1)[-1].rsplit('.', 1)[0]
    stem = re.sub(r'[^A-Za-z0-9_-]+', '-', stem).strip('-_')[:100] or 'video'
    return stem + '.' + _MIME_EXTENSIONS[mime]


def playback_url(key, mime, filename):
    mime = _mime(mime)
    params = _object_params(key) | {'ResponseContentType': mime,
                                    'ResponseContentDisposition': 'inline; filename="' + _filename(filename, mime) + '"',
                                    'ResponseCacheControl': 'private, no-store'}
    return _signed_url(client().generate_presigned_url('get_object', Params=params,
                                                       ExpiresIn=PLAYBACK_URL_SECONDS, HttpMethod='GET'))


def _vint(data, offset, identifier=False):
    if offset >= len(data) or not data[offset]:
        raise ValueError
    mask, length = 0x80, 1
    while not data[offset] & mask:
        mask >>= 1
        length += 1
    if length > (4 if identifier else 8) or offset + length > len(data):
        raise ValueError
    value = data[offset] if identifier else data[offset] & (mask - 1)
    for byte in data[offset + 1:offset + length]:
        value = (value << 8) | byte
    if not identifier and value == (1 << (7 * length)) - 1:
        raise ValueError
    return value, offset + length


def _webm(data):
    try:
        length, offset = _vint(data, 4)
        end = offset + length
        if end > len(data) or end > 4096:
            return False
        doctypes = []
        while offset < end:
            ident, cursor = _vint(data, offset, identifier=True)
            size, cursor = _vint(data, cursor)
            if cursor + size > end:
                return False
            if ident == 0x4282:
                doctypes.append(data[cursor:cursor + size])
            offset = cursor + size
        return doctypes == [b'webm']
    except ValueError:
        return False


def _iso_video(data):
    accepted = {b'isom', b'iso2', b'iso3', b'iso4', b'iso5', b'iso6', b'mp41', b'mp42',
                b'avc1', b'dash', b'M4V ', b'M4VH', b'M4VP', b'MSNV'}
    offset = 0
    while offset + 8 <= len(data) and offset < 4096:
        size = int.from_bytes(data[offset:offset + 4], 'big')
        box_type = data[offset + 4:offset + 8]
        header = 8
        if size == 1:
            if offset + 16 > len(data):
                return ''
            size, header = int.from_bytes(data[offset + 8:offset + 16], 'big'), 16
        if size < header or offset + size > len(data) or offset + size > 4096:
            return ''
        if box_type == b'ftyp':
            payload = data[offset + header:offset + size]
            if len(payload) < 8 or (len(payload) - 8) % 4:
                return ''
            major = payload[:4]
            if major == b'qt  ':
                return 'video/quicktime'
            # Image containers use the same ISO framing but are never video.
            if major in {b'avif', b'avis', b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1'}:
                return ''
            brands = {major} | {payload[i:i + 4] for i in range(8, len(payload), 4)}
            return 'video/mp4' if brands & accepted else ''
        if box_type not in {b'free', b'wide', b'skip'}:
            return ''
        offset += size
    return ''


def sniff_video(data, mime=None):
    """Check bounded container metadata; this does not scan video content."""
    result = ''
    if isinstance(data, bytes):
        data = data[:4096]
        if data.startswith(b'\x1a\x45\xdf\xa3'):
            result = 'video/webm' if _webm(data) else ''
        else:
            result = _iso_video(data)
    if mime is None:
        return result
    try:
        return bool(result and result == _mime(mime))
    except ValueError:
        return False
