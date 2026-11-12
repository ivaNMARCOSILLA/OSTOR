"""Private in-memory R2 for the isolated video browser suite only.

The production application never imports this module. Browser requests to a fake
R2 hostname are intercepted by Playwright and forwarded to these nonce-bound
loopback routes, so the actual file bytes exercise the real multipart checks.
"""
import hashlib
import io
import re
import secrets
import threading
import time
from urllib.parse import quote
from unittest.mock import patch

from botocore.exceptions import ClientError
from flask import Response, jsonify, request


HOST = 'video-browser.r2.cloudflarestorage.com'


def missing(operation):
    return ClientError({'Error': {'Code': 'NoSuchKey', 'Message': 'Missing isolated video fixture'}}, operation)


class VideoUploadFixture:
    def __init__(self, app):
        self.nonce = secrets.token_urlsafe(24)
        self.lock = threading.RLock()
        self.uploads = {}
        self.objects = {}
        self.tickets = {}
        self.patches = []
        settings = {
            'OL_VIDEOS_ENABLED': '1', 'VIDEO_STORAGE_PRIVATE_CONFIRMED': '1',
            'VIDEO_R2_ENDPOINT': 'https://' + HOST,
            'VIDEO_R2_BUCKET': 'isolated-community-videos',
            'VIDEO_R2_ACCESS_KEY_ID': 'isolated-browser-access',
            'VIDEO_R2_SECRET_ACCESS_KEY': 'isolated-browser-secret',
            'VIDEO_MAX_BYTES': '',
        }
        import video_storage
        self.patches = [patch.dict('os.environ', settings), patch.object(video_storage, 'client', return_value=self)]
        for item in self.patches:
            item.start()
        prefix = '/__video_fixture__/' + self.nonce
        suffix = secrets.token_hex(8)
        app.add_url_rule(prefix + '/part/<upload_id>/<int:number>', 'fixture_video_part_' + suffix,
                         self.receive_part, methods=['PUT'])
        app.add_url_rule(prefix + '/media/<ticket>', 'fixture_video_media_' + suffix,
                         self.media, methods=['GET', 'HEAD'])

    def close(self):
        for item in reversed(self.patches):
            item.stop()
        self.patches.clear()

    def create_multipart_upload(self, *, Bucket, Key, ContentType, **kwargs):
        with self.lock:
            ident = secrets.token_hex(18)
            self.uploads[ident] = {'key': Key, 'mime': ContentType, 'parts': {}}
            return {'UploadId': ident}

    def generate_presigned_url(self, operation, *, Params, ExpiresIn, HttpMethod):
        with self.lock:
            if operation == 'upload_part':
                upload = self.uploads.get(Params['UploadId'])
                if not upload or upload['key'] != Params['Key']:
                    raise missing('UploadPart')
                path = '/part/' + Params['UploadId'] + '/' + str(Params['PartNumber'])
            elif operation == 'get_object':
                if Params['Key'] not in self.objects:
                    raise missing('GetObject')
                ticket = secrets.token_urlsafe(24)
                self.tickets[ticket] = {'key': Params['Key'], 'expires': time.monotonic() + ExpiresIn}
                path = '/media/' + quote(ticket, safe='')
            else:
                raise AssertionError('Unexpected fixture signing operation: ' + operation)
            return 'https://' + HOST + '/' + self.nonce + path + '?X-Amz-Expires=' + str(ExpiresIn)

    def receive_part(self, upload_id, number):
        # This exception belongs solely to the loopback test route. The actual
        # application's API metadata limit remains unchanged at 64 KiB.
        request.max_content_length = 16 * 1024 * 1024
        data = request.get_data(cache=False)
        with self.lock:
            upload = self.uploads.get(upload_id)
            if not upload or not 1 <= number <= 10000:
                return jsonify(error='Missing isolated upload'), 404
            etag = '"' + hashlib.sha256(data).hexdigest() + '"'
            upload['parts'][number] = {'data': data, 'ETag': etag}
        return Response(status=200, headers={'ETag': etag})

    def list_parts(self, *, Bucket, Key, UploadId, MaxParts=1000, PartNumberMarker=0):
        with self.lock:
            upload = self.uploads.get(UploadId)
            if not upload or upload['key'] != Key:
                raise missing('ListParts')
            parts = [{'PartNumber': number, 'Size': len(value['data']), 'ETag': value['ETag']}
                     for number, value in sorted(upload['parts'].items()) if number > PartNumberMarker]
            selected = parts[:MaxParts]
            return {'Parts': selected, 'IsTruncated': len(parts) > len(selected),
                    'NextPartNumberMarker': selected[-1]['PartNumber'] if selected else PartNumberMarker}

    def complete_multipart_upload(self, *, Bucket, Key, UploadId, MultipartUpload):
        with self.lock:
            upload = self.uploads.get(UploadId)
            if not upload or upload['key'] != Key:
                raise missing('CompleteMultipartUpload')
            values = []
            for part in MultipartUpload['Parts']:
                value = upload['parts'].get(part['PartNumber'])
                if not value or value['ETag'] != part['ETag']:
                    raise missing('CompleteMultipartUpload')
                values.append(value['data'])
            data = b''.join(values)
            etag = '"' + hashlib.sha256(data).hexdigest() + '"'
            self.objects[Key] = {'data': data, 'mime': upload['mime'], 'ETag': etag}
            del self.uploads[UploadId]
            return {'ETag': etag}

    def abort_multipart_upload(self, *, Bucket, Key, UploadId):
        with self.lock:
            upload = self.uploads.get(UploadId)
            if upload and upload['key'] == Key:
                del self.uploads[UploadId]
            return {}

    def delete_object(self, *, Bucket, Key):
        with self.lock:
            self.objects.pop(Key, None)
            return {}

    def head_object(self, *, Bucket, Key):
        with self.lock:
            value = self.objects.get(Key)
            if not value:
                raise missing('HeadObject')
            return {'ContentLength': len(value['data']), 'ContentType': value['mime'], 'ETag': value['ETag']}

    def get_object(self, *, Bucket, Key, Range=None):
        with self.lock:
            value = self.objects.get(Key)
            if not value:
                raise missing('GetObject')
            data = value['data']
            if Range:
                match = re.fullmatch(r'bytes=(\d+)-(\d+)', Range)
                if not match:
                    raise AssertionError('Unexpected fixture sample range')
                data = data[int(match[1]):int(match[2]) + 1]
            return {'Body': io.BytesIO(data), 'ContentType': value['mime']}

    def media(self, ticket):
        with self.lock:
            signed = self.tickets.get(ticket)
            value = self.objects.get(signed['key']) if signed and signed['expires'] >= time.monotonic() else None
            if not value:
                return Response(status=404)
            data, mime = value['data'], value['mime']
        total = len(data)
        headers = {'Accept-Ranges': 'bytes', 'Cache-Control': 'private, no-store'}
        range_header = request.headers.get('Range')
        status = 200
        if range_header:
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', range_header)
            if not match or int(match[1]) >= total:
                return Response(status=416, headers={'Content-Range': 'bytes */' + str(total)})
            first = int(match[1]);last = min(int(match[2]) if match[2] else total - 1, total - 1)
            headers['Content-Range'] = f'bytes {first}-{last}/{total}'
            data = data[first:last + 1]
            status = 206
        return Response(data, status=status, mimetype=mime,
                        headers=headers | {'Content-Length': str(len(data))})


def install(app):
    return VideoUploadFixture(app)
