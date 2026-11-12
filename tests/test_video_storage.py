"""Multipart videos stay private and bounded without connecting to R2."""
import io
import os
import unittest
from unittest.mock import MagicMock, patch

import video_storage as storage


ENDPOINT = 'https://account.eu.r2.cloudflarestorage.com'
KEY = 'videos/quarantine/0123456789abcdef0123456789abcdef.mp4'
ENV = {'OL_VIDEOS_ENABLED': '1', 'VIDEO_STORAGE_PRIVATE_CONFIRMED': '1',
       'VIDEO_R2_ENDPOINT': ENDPOINT, 'VIDEO_R2_BUCKET': 'community-video-bucket',
       'VIDEO_R2_ACCESS_KEY_ID': 'private-test-access', 'VIDEO_R2_SECRET_ACCESS_KEY': 'private-test-secret'}


def mp4(major=b'isom', compatible=b'mp42'):
    payload = major + b'\x00\x00\x00\x00' + compatible
    return (len(payload) + 8).to_bytes(4, 'big') + b'ftyp' + payload


def webm(doctype=b'webm'):
    payload = b'\x42\x82' + bytes([0x80 | len(doctype)]) + doctype
    return b'\x1a\x45\xdf\xa3' + bytes([0x80 | len(payload)]) + payload


class VideoStorageTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, ENV, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_configuration_is_private_and_disabled_until_explicitly_enabled(self):
        info = storage.configuration()
        self.assertTrue(info['storage_ready'])
        self.assertEqual(info['max_file_bytes'], 5 * 1024 ** 4)
        self.assertEqual(set(info['allowed_mime_types']), {'video/mp4', 'video/webm', 'video/quicktime'})
        for value in (ENDPOINT, ENV['VIDEO_R2_BUCKET'], ENV['VIDEO_R2_ACCESS_KEY_ID'], ENV['VIDEO_R2_SECRET_ACCESS_KEY']):
            self.assertNotIn(value, str(info))
        for flag in ('OL_VIDEOS_ENABLED', 'VIDEO_STORAGE_PRIVATE_CONFIRMED'):
            with self.subTest(flag=flag), patch.dict(os.environ, {flag: '0'}):
                self.assertFalse(storage.ready())
                with self.assertRaisesRegex(RuntimeError, 'video_storage_not_ready'):
                    storage.client()

    def test_endpoint_rejects_foreign_credentials_ports_and_ambiguous_urls(self):
        for endpoint in [
            'http://account.r2.cloudflarestorage.com', 'https://account.r2.cloudflarestorage.com.attacker.test',
            'https://account.r2.cloudflarestorage.com/path', 'https://user@account.r2.cloudflarestorage.com',
            'https://@account.r2.cloudflarestorage.com', ENDPOINT + '?', ENDPOINT + '#',
            ENDPOINT + ':8443', 'https://account..r2.cloudflarestorage.com',
            'https://account.r2.cloudflarestorage.com\n.evil.test', 'https://account.r2.cloudflarestorage.com:broken',
        ]:
            with self.subTest(endpoint=endpoint), patch.dict(os.environ, {'VIDEO_R2_ENDPOINT': endpoint}):
                self.assertFalse(storage.ready())
        with patch.dict(os.environ, {'VIDEO_R2_ENDPOINT': ENDPOINT + ':443/'}):
            self.assertTrue(storage.ready())

    def test_bucket_names_are_not_paths(self):
        for name in ['../../private', 'a', 'ALL-VIDEOS', 'videos/path', 'video.bucket', '-videos', 'videos-']:
            with self.subTest(name=name), patch.dict(os.environ, {'VIDEO_R2_BUCKET': name}):
                self.assertFalse(storage.ready())

    def test_generic_recording_credentials_can_be_explicitly_reused(self):
        generic = {key.removeprefix('VIDEO_'): value for key, value in ENV.items() if key.startswith('VIDEO_R2_')}
        generic.update(OL_VIDEOS_ENABLED='1', VIDEO_STORAGE_PRIVATE_CONFIRMED='1')
        with patch.dict(os.environ, generic, clear=True):
            self.assertTrue(storage.ready())
            with patch.dict(os.environ, {'VIDEO_R2_BUCKET': 'separate-videos'}), patch('boto3.client') as factory:
                storage.client()
                self.assertEqual(factory.call_args.kwargs['endpoint_url'], ENDPOINT)
                self.assertEqual(factory.call_args.kwargs['aws_access_key_id'], 'private-test-access')

    def test_client_uses_explicit_keys_tls_sigv4_and_path_style(self):
        with patch('boto3.client') as factory:
            storage.client()
        self.assertEqual(factory.call_args.args, ('s3',))
        options = factory.call_args.kwargs
        self.assertEqual(options['region_name'], 'auto')
        self.assertEqual(options['config'].signature_version, 's3v4')
        self.assertEqual(options['config'].connect_timeout, 3)
        self.assertEqual(options['config'].read_timeout, 10)
        self.assertEqual(options['config'].s3['addressing_style'], 'path')

    def test_multipart_plan_has_no_small_application_file_or_duration_quota(self):
        mib = 1024 ** 2
        for size in [1, 8 * mib, 8 * mib + 1, 9 * 1024 ** 3, storage.MAX_FILE_BYTES]:
            with self.subTest(size=size):
                plan = storage.multipart_plan(size)
                self.assertGreaterEqual(plan['part_size'], 8 * mib)
                self.assertEqual(plan['part_size'] % mib, 0)
                self.assertLessEqual(plan['part_count'], 10000)
                self.assertGreaterEqual(plan['part_size'] * plan['part_count'], size)
                self.assertLess((plan['part_count'] - 1) * plan['part_size'], size)
        for invalid in [True, False, 0, -1, '100', 2.5, storage.MAX_FILE_BYTES + 1]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                storage.multipart_plan(invalid)

    def test_optional_storage_limit_is_validated_and_fails_closed(self):
        with patch.dict(os.environ, {'VIDEO_MAX_BYTES': '123456789'}):
            self.assertEqual(storage.configuration()['max_file_bytes'], 123456789)
            with self.assertRaises(ValueError):
                storage.multipart_plan(123456790)
        for value in ['0', '-1', 'unlimited', '9.2', '999999999999999999999999999999']:
            with self.subTest(value=value), patch.dict(os.environ, {'VIDEO_MAX_BYTES': value}):
                self.assertFalse(storage.ready())
                with self.assertRaises(ValueError):
                    storage.multipart_plan(1)

    def test_start_and_signatures_can_only_write_multipart_video_objects(self):
        fake = MagicMock()
        fake.create_multipart_upload.return_value = {'UploadId': 'opaque-upload-id'}
        fake.generate_presigned_url.return_value = ENDPOINT + '/community-video-bucket/' + KEY + '?signature=test'
        with patch.object(storage, 'client', return_value=fake):
            self.assertEqual(storage.start(KEY, 'video/mp4'), 'opaque-upload-id')
            storage.presign_part(KEY, 'opaque-upload-id', 1)
        options = fake.create_multipart_upload.call_args.kwargs
        self.assertEqual(options['ContentType'], 'video/mp4')
        self.assertEqual(options['CacheControl'], 'private, no-store')
        self.assertNotIn('ACL', options)
        signed = fake.generate_presigned_url.call_args
        self.assertEqual(signed.args, ('upload_part',))
        self.assertEqual(signed.kwargs['ExpiresIn'], 600)
        self.assertEqual(signed.kwargs['HttpMethod'], 'PUT')
        self.assertEqual(signed.kwargs['Params']['PartNumber'], 1)
        self.assertFalse(fake.put_object.called)

    def test_invalid_object_ids_cannot_escape_the_video_prefix(self):
        fake = MagicMock()
        with patch.object(storage, 'client', return_value=fake):
            for key in ['directos/secret.mp4', '/videos/x.mp4', 'videos/../secret.mp4',
                        'videos/one//video.mp4', 'videos/%2e%2e/private', 'videos/\\private', 'videos/end/']:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    storage.start(key, 'video/mp4')
            for number in [True, 0, 10001, '1', 1.5]:
                with self.subTest(number=number), self.assertRaises(ValueError):
                    storage.presign_part(KEY, 'upload', number)
            with self.assertRaises(ValueError):
                storage.start(KEY, 'text/html')
        self.assertFalse(fake.create_multipart_upload.called)
        self.assertFalse(fake.generate_presigned_url.called)

    def test_list_parts_follows_pagination_and_keeps_server_sizes(self):
        fake = MagicMock()
        fake.list_parts.side_effect = [
            {'Parts': [{'PartNumber': 1, 'Size': 8 * 1024 ** 2, 'ETag': '"server-one"'}],
             'IsTruncated': True, 'NextPartNumberMarker': 1},
            {'Parts': [{'PartNumber': 2, 'Size': 312, 'ETag': '"server-two"'}], 'IsTruncated': False},
        ]
        with patch.object(storage, 'client', return_value=fake):
            parts = storage.list_parts(KEY, 'upload')
        self.assertEqual([part['PartNumber'] for part in parts], [1, 2])
        self.assertEqual(parts[1]['Size'], 312)
        self.assertEqual(fake.list_parts.call_args.kwargs['PartNumberMarker'], 1)

    def test_list_parts_rejects_duplicate_or_stalled_server_pages(self):
        bad_responses = [
            [{'Parts': [], 'IsTruncated': True, 'NextPartNumberMarker': 0}],
            [{'Parts': [{'PartNumber': 1, 'Size': 2, 'ETag': 'one'}], 'IsTruncated': True, 'NextPartNumberMarker': 1},
             {'Parts': [{'PartNumber': 1, 'Size': 2, 'ETag': 'one'}], 'IsTruncated': False}],
            [{'Parts': [{'PartNumber': 1, 'Size': 0, 'ETag': 'one'}], 'IsTruncated': False}],
        ]
        for responses in bad_responses:
            fake = MagicMock()
            fake.list_parts.side_effect = responses
            with self.subTest(responses=responses), patch.object(storage, 'client', return_value=fake):
                with self.assertRaises(RuntimeError):
                    storage.list_parts(KEY, 'upload')

    def test_complete_only_uses_consecutive_server_etags(self):
        fake = MagicMock()
        fake.complete_multipart_upload.return_value = {'ETag': '"complete-etag"'}
        parts = [{'PartNumber': 1, 'Size': 9, 'ETag': '"server-one"'}, {'PartNumber': 2, 'ETag': '"server-two"'}]
        with patch.object(storage, 'client', return_value=fake):
            self.assertEqual(storage.complete(KEY, 'upload', parts), '"complete-etag"')
            for invalid in [[], [{'PartNumber': 2, 'ETag': 'two'}], [{'PartNumber': 1, 'ETag': 'bad\nheader'}]]:
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    storage.complete(KEY, 'upload', invalid)
        self.assertEqual(fake.complete_multipart_upload.call_count, 1)
        self.assertEqual(fake.complete_multipart_upload.call_args.kwargs['MultipartUpload']['Parts'],
                         [{'PartNumber': 1, 'ETag': '"server-one"'}, {'PartNumber': 2, 'ETag': '"server-two"'}])

    def test_sample_only_reads_a_bounded_range_and_always_closes(self):
        class Body(io.BytesIO):
            requested = None
            def read(self, amount=-1):
                self.requested = amount
                return super().read(amount)
        body = Body(mp4() + b'\x00' * 10000)
        fake = MagicMock()
        fake.get_object.return_value = {'Body': body, 'ContentLength': 1000000000}
        with patch.object(storage, 'client', return_value=fake):
            content = storage.sample(KEY)
        self.assertEqual(len(content), 4096)
        self.assertEqual(body.requested, 4096)
        self.assertTrue(body.closed)
        self.assertEqual(fake.get_object.call_args.kwargs['Range'], 'bytes=0-4095')

    def test_head_deletion_and_abort_keep_the_stored_key(self):
        fake = MagicMock()
        fake.head_object.return_value = {'ContentLength': 34, 'ContentType': 'video/mp4; codecs=avc1', 'ETag': 'etag', 'Private': 'not-returned'}
        with patch.object(storage, 'client', return_value=fake):
            self.assertEqual(storage.head(KEY), {'ContentLength': 34, 'ContentType': 'video/mp4', 'ETag': 'etag'})
            storage.abort(KEY, 'upload')
            storage.delete(KEY)
        self.assertEqual(fake.abort_multipart_upload.call_args.kwargs['UploadId'], 'upload')
        self.assertEqual(fake.delete_object.call_args.kwargs['Key'], KEY)

    def test_playback_url_has_short_expiry_safe_filename_and_canonical_type(self):
        fake = MagicMock()
        fake.generate_presigned_url.return_value = ENDPOINT + '/community-video-bucket/' + KEY + '?signature=test'
        with patch.object(storage, 'client', return_value=fake):
            storage.playback_url(KEY, 'video/mp4', '../unsafe";\r\nfile.html')
            with self.assertRaises(ValueError):
                storage.playback_url(KEY, 'text/html', 'video.html')
        call = fake.generate_presigned_url.call_args
        self.assertEqual(call.args, ('get_object',))
        self.assertEqual(call.kwargs['ExpiresIn'], 60)
        self.assertEqual(call.kwargs['HttpMethod'], 'GET')
        params = call.kwargs['Params']
        self.assertEqual(params['ResponseContentType'], 'video/mp4')
        self.assertEqual(params['ResponseCacheControl'], 'private, no-store')
        self.assertEqual(params['ResponseContentDisposition'], 'inline; filename="unsafe-file.mp4"')

    def test_presigned_links_cannot_redirect_to_foreign_hosts(self):
        fake = MagicMock()
        for url in ['https://attacker.test/file', 'http://account.eu.r2.cloudflarestorage.com/file',
                    ENDPOINT + '/file#fragment', 'https://name@account.eu.r2.cloudflarestorage.com/file']:
            fake.generate_presigned_url.return_value = url
            with self.subTest(url=url), patch.object(storage, 'client', return_value=fake):
                with self.assertRaises(RuntimeError):
                    storage.playback_url(KEY, 'video/mp4', 'safe')

    def test_real_presigning_is_local_and_does_not_disclose_secret(self):
        from urllib.parse import urlsplit, parse_qs
        url = storage.playback_url(KEY, 'video/mp4', 'safe')
        self.assertEqual(urlsplit(url).hostname, 'account.eu.r2.cloudflarestorage.com')
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query['X-Amz-Expires'], ['60'])
        self.assertEqual(query['response-content-type'], ['video/mp4'])
        self.assertNotIn(ENV['VIDEO_R2_SECRET_ACCESS_KEY'], url)

    def test_container_checks_distinguish_real_declared_video_formats(self):
        self.assertEqual(storage.sniff_video(mp4()), 'video/mp4')
        self.assertTrue(storage.sniff_video(mp4(), 'video/mp4'))
        self.assertTrue(storage.sniff_video(mp4(b'qt  '), 'video/quicktime'))
        self.assertTrue(storage.sniff_video(webm(), 'video/webm'))
        self.assertFalse(storage.sniff_video(mp4(), 'video/webm'))
        self.assertFalse(storage.sniff_video(webm(), 'video/mp4'))
        self.assertFalse(storage.sniff_video(mp4(), 'text/html'))
        leading_free = (8).to_bytes(4, 'big') + b'free'
        self.assertTrue(storage.sniff_video(leading_free + mp4(), 'video/mp4'))

    def test_container_checks_reject_html_images_matroska_and_incomplete_headers(self):
        samples = [b'<!doctype html><script>bad()</script>', b'<svg onload="bad()"/>', b'',
                   b'\x00\x00\x00\x18ftyp', mp4(b'avif', b'isom'), mp4(b'heic', b'isom'),
                   mp4(b'bad!', b'nope'), webm(b'matroska'), b'\x1a\x45\xdf\xa3\xffwebm',
                   b'prefix' + mp4(), bytearray(mp4()), b'\x1a\x45\xdf\xa3\x87\x42\x82\x84we']
        for content in samples:
            with self.subTest(content=content):
                self.assertEqual(storage.sniff_video(content), '')
                self.assertFalse(storage.sniff_video(content, 'video/mp4'))


if __name__ == '__main__':
    unittest.main()
