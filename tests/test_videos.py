"""Quarantine is an authorization boundary, not a delay before auto-publication."""
import secrets
import unittest
from datetime import timedelta
from unittest.mock import patch

import app as application
import membership as m
import videos as v
from auth_support import authenticated_client


MP4 = b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42'


class FakeStore:
    def __init__(self):
        self.uploads = {}; self.objects = {}; self.calls = []

    def start(self, key, mime):
        ident = secrets.token_hex(16)
        self.uploads[ident] = {'key': key, 'mime': mime, 'parts': []}
        self.calls.append(('start', key)); return ident

    def presign_part(self, key, ident, number):
        self.calls.append(('part', key, number))
        return 'https://fixture.r2.cloudflarestorage.com/private-part?number=' + str(number)

    def list_parts(self, key, ident):
        self.calls.append(('list', key)); return list(self.uploads[ident]['parts'])

    def complete(self, key, ident, parts):
        upload = self.uploads.pop(ident)
        self.objects[key] = {'ContentLength': sum(part['Size'] for part in upload['parts']),
                             'ContentType': upload['mime'], 'ETag': '"verified-etag"', 'body': MP4}
        self.calls.append(('complete', key)); return 'verified-etag'

    def head(self, key):
        self.calls.append(('head', key))
        return {k: val for k, val in self.objects[key].items() if k != 'body'}

    def sample(self, key, limit=4096):
        self.calls.append(('sample', key)); return self.objects[key]['body'][:limit]

    def abort(self, key, ident):
        self.uploads.pop(ident, None); self.calls.append(('abort', key))

    def delete(self, key):
        self.objects.pop(key, None); self.calls.append(('delete', key))

    def playback_url(self, key, mime, filename):
        self.calls.append(('play', key, mime, filename))
        return 'https://fixture.r2.cloudflarestorage.com/private-media?expires=60'


class VideoQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.app = application.app
        self.admin = authenticated_client(self.app, self.addCleanup)
        with self.app.app_context():
            v.init_database()
        self.author, self.owner_id = self.account('video-author')
        self.other, self.other_id = self.account('video-viewer')
        self.guest = self.app.test_client()
        self.store = FakeStore()
        settings = {'storage_ready': True, 'max_file_bytes': 5 * 1024 ** 4,
                    'allowed_mime_types': list(v.MIME_EXTENSIONS)}
        for name, replacement in [('ready', lambda: True), ('configuration', lambda: settings)]:
            fixture = patch.object(v.storage, name, side_effect=replacement)
            fixture.start(); self.addCleanup(fixture.stop)
        for name in ['start', 'presign_part', 'list_parts', 'complete', 'head', 'sample', 'abort', 'delete', 'playback_url']:
            fixture = patch.object(v.storage, name, side_effect=getattr(self.store, name))
            fixture.start(); self.addCleanup(fixture.stop)

    def account(self, username):
        ident = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute("INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,'member',?)",
                         (ident, username, 'fixture-not-a-password', m.stamp(m.now_utc())))
            conn.execute('INSERT INTO member_profiles(member_id,email,nickname,updated_at) VALUES(?,?,?,?)',
                         (ident, username + '@example.invalid', 'Nombre público', m.stamp(m.now_utc())))
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['member_id'] = ident; session['session_version'] = 0
        return client, ident

    def post(self, client, path, data=None):
        token = client.get('/api/account/me').json['csrf']
        return client.post(path, json={} if data is None else data, headers={'X-CSRF-Token': token})

    def begin(self, **changes):
        data = {'title': 'Mi baile', 'description': 'Una creación propia.', 'category': 'dance',
                'filename': '../../mi-baile.mp4', 'size_bytes': len(MP4), 'mime_type': 'video/mp4', 'rights_confirmed': True}
        data.update(changes)
        response = self.post(self.author, '/api/videos/uploads', data)
        self.assertEqual(response.status_code, 201, response.json)
        ident = response.json['id']; row = self.row(ident)
        self.store.uploads[row['upload_id']]['parts'] = [
            {'PartNumber': number, 'ETag': '"part-' + str(number) + '"',
             'Size': min(row['part_size'], row['size_bytes'] - (number - 1) * row['part_size'])}
            for number in range(1, row['part_count'] + 1)]
        return ident

    def row(self, ident):
        with self.app.app_context(), m.database() as conn:
            return dict(conn.execute('SELECT * FROM community_videos WHERE id=?', (ident,)).fetchone())

    def finish(self, ident):
        response = self.post(self.author, '/api/videos/uploads/' + ident + '/complete', {'parts': [{'ETag': 'client-spoof'}]})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['video']['state'], 'quarantined')
        return response

    def approve(self, ident):
        response = self.post(self.admin, '/api/admin/videos/' + ident + '/review', {'decision': 'approve', 'review_confirmed': True})
        self.assertEqual(response.status_code, 200, response.json)
        return response

    def test_public_reading_and_free_account_upload_boundaries(self):
        self.assertEqual(self.guest.get('/api/videos').status_code, 200)
        self.assertEqual(self.guest.get('/api/videos/config').status_code, 200)
        self.assertEqual(self.guest.get('/api/videos/me').status_code, 401)
        self.assertEqual(self.post(self.guest, '/api/videos/uploads').status_code, 401)
        self.assertEqual(self.other.get('/api/admin/videos').status_code, 403)
        self.assertFalse(self.author.get('/api/account/me').json['user']['active'])
        ident = self.begin()
        self.assertEqual(self.row(ident)['owner_id'], self.owner_id)
        self.assertTrue(self.row(ident)['object_key'].startswith('videos/' + self.owner_id + '/'))
        self.assertNotIn('..', self.row(ident)['object_key'])

    def test_csrf_and_strict_metadata_are_required(self):
        self.assertEqual(self.author.open('/api/videos/uploads', method='POST', json={}).status_code, 403)
        base = {'title': 'Vídeo', 'category': 'other', 'filename': 'video.mp4', 'mime_type': 'video/mp4', 'size_bytes': len(MP4), 'rights_confirmed': True}
        for change in [{'rights_confirmed': 'true'}, {'size_bytes': True}, {'title': 'x' * 161}, {'description': []}, {'category': 'unknown'}, {'mime_type': 'text/html'}]:
            response = self.post(self.author, '/api/videos/uploads', base | change)
            self.assertEqual(response.status_code, 400, (change, response.json))
        self.assertFalse(self.store.calls)

    def test_unconfigured_storage_does_not_fabricate_an_upload(self):
        with patch.object(v.storage, 'ready', return_value=False):
            response = self.post(self.author, '/api/videos/uploads', {})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.store.calls)
        self.assertEqual(self.author.get('/api/videos/me').json['total'], 0)

    def test_malformed_review_decisions_do_not_change_quarantined_video(self):
        ident = self.begin(); self.finish(ident)
        for decision in [None, [], {}, True, 1, 'published']:
            response = self.post(self.admin, '/api/admin/videos/' + ident + '/review',
                                 {'decision': decision, 'review_confirmed': True})
            self.assertEqual(response.status_code, 400, (decision, response.json))
            self.assertEqual(self.row(ident)['state'], 'quarantined')
        self.assertEqual(self.guest.get('/api/videos').json['total'], 0)
        with self.app.app_context(), m.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM community_video_reviews WHERE video_id=?', (ident,)).fetchone()['n'], 0)

    def test_part_links_are_bound_to_the_owner_and_expected_part(self):
        ident = self.begin()
        self.assertEqual(self.post(self.other, '/api/videos/uploads/' + ident + '/parts', {'part_number': 1}).status_code, 404)
        for number in [0, 2, True, '1']:
            self.assertEqual(self.post(self.author, '/api/videos/uploads/' + ident + '/parts', {'part_number': number}).status_code, 400)
        self.assertEqual(self.post(self.author, '/api/videos/uploads/' + ident + '/parts', {'part_number': 1}).status_code, 200)
        own = self.author.get('/api/videos/me').json
        for forbidden in ['object_key', 'upload_id', 'private-part', 'verified_etag']:
            self.assertNotIn(forbidden, str(own))

    def test_incomplete_or_wrong_parts_never_finalize_or_publish(self):
        ident = self.begin(size_bytes=9 * 1024 ** 2)
        row = self.row(ident); parts = self.store.uploads[row['upload_id']]['parts']
        self.store.uploads[row['upload_id']]['parts'] = parts[:1]
        self.assertEqual(self.post(self.author, '/api/videos/uploads/' + ident + '/complete').status_code, 409)
        self.assertEqual(self.row(ident)['state'], 'uploading')
        self.store.uploads[row['upload_id']]['parts'] = [dict(part) for part in parts]
        self.store.uploads[row['upload_id']]['parts'][1]['Size'] += 1
        self.assertEqual(self.post(self.author, '/api/videos/uploads/' + ident + '/complete').status_code, 409)
        self.assertNotIn(('complete', row['object_key']), self.store.calls)
        self.assertEqual(self.guest.get('/api/videos').json['total'], 0)

    def test_quarantine_is_private_until_confirmed_admin_review(self):
        ident = self.begin(); self.finish(ident)
        self.assertEqual(self.guest.get('/api/videos').json['total'], 0)
        for client in [self.guest, self.author, self.other]:
            self.assertEqual(client.get('/api/videos/' + ident + '/play').status_code, 404)
        self.assertEqual(self.author.get('/api/admin/videos/' + ident + '/preview').status_code, 403)
        preview = self.admin.get('/api/admin/videos/' + ident + '/preview')
        self.assertEqual(preview.status_code, 302)
        self.assertEqual(preview.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.post(self.admin, '/api/admin/videos/' + ident + '/review', {'decision': 'approve'}).status_code, 400)
        self.assertEqual(self.post(self.author, '/api/admin/videos/' + ident + '/review', {'decision': 'approve', 'review_confirmed': True}).status_code, 403)
        self.approve(ident)
        public = self.guest.get('/api/videos').json
        self.assertEqual(public['total'], 1)
        self.assertEqual(public['videos'][0]['author'], {'username': 'video-author', 'nickname': 'Nombre público'})
        for forbidden in ['object_key', 'upload_id', 'review_reason', 'reporter_id', '@example.invalid']:
            self.assertNotIn(forbidden, str(public))
        self.assertEqual(self.guest.get('/api/videos/' + ident + '/play').status_code, 302)

    def test_renamed_html_is_rejected_and_cannot_be_previewed_or_approved(self):
        ident = self.begin(); original = self.store.complete
        def malicious(*args):
            result = original(*args); self.store.objects[args[0]]['body'] = b'<html><script>attack()</script></html>'; return result
        with patch.object(v.storage, 'complete', side_effect=malicious):
            result = self.post(self.author, '/api/videos/uploads/' + ident + '/complete')
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.row(ident)['state'], 'rejected')
        self.assertFalse(self.row(ident)['technical_checked'])
        self.assertEqual(self.admin.get('/api/admin/videos/' + ident + '/preview').status_code, 404)
        self.assertEqual(self.post(self.admin, '/api/admin/videos/' + ident + '/review', {'decision': 'approve', 'review_confirmed': True}).status_code, 409)

    def test_approval_rechecks_exact_verified_object(self):
        ident = self.begin(); self.finish(ident)
        key = self.row(ident)['object_key']; self.store.objects[key]['ETag'] = '"changed"'
        result = self.post(self.admin, '/api/admin/videos/' + ident + '/review', {'decision': 'approve', 'review_confirmed': True})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.row(ident)['state'], 'quarantined')

    def test_requarantine_and_rejection_are_recorded_and_stop_public_links(self):
        ident = self.begin(); self.finish(ident); self.approve(ident)
        endpoint = '/api/admin/videos/' + ident + '/review'
        self.assertEqual(self.post(self.admin, endpoint, {'decision': 'quarantine'}).status_code, 400)
        self.assertEqual(self.post(self.admin, endpoint, {'decision': 'quarantine', 'reason': 'Necesita otra revisión.'}).status_code, 200)
        self.assertEqual(self.guest.get('/api/videos/' + ident + '/play').status_code, 404)
        self.assertEqual(self.post(self.admin, endpoint, {'decision': 'reject', 'reason': 'No cumple las condiciones.'}).status_code, 200)
        with self.app.app_context(), m.database() as conn:
            states = [row['new_state'] for row in conn.execute('SELECT new_state FROM community_video_reviews WHERE video_id=? ORDER BY created_at,id', (ident,)).fetchall()]
        self.assertCountEqual(states, ['published', 'quarantined', 'rejected'])

    def test_same_second_review_race_is_blocked_by_revision(self):
        ident = self.begin(); self.finish(ident)
        original = self.store.head
        def changed_during_head(key):
            response = self.post(self.admin, '/api/admin/videos/' + ident + '/review', {'decision': 'quarantine', 'reason': 'Revisar de nuevo.'})
            self.assertEqual(response.status_code, 200)
            return original(key)
        with patch.object(v.storage, 'head', side_effect=changed_during_head):
            response = self.post(self.admin, '/api/admin/videos/' + ident + '/review', {'decision': 'approve', 'review_confirmed': True})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.row(ident)['review_reason'], 'Revisar de nuevo.')

    def test_expired_completion_lease_allows_part_retry(self):
        ident = self.begin()
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE community_videos SET operation_token=?,operation_expires_at=? WHERE id=?',
                         ('crashed-completer', m.stamp(m.now_utc() - timedelta(minutes=1)), ident))
        result = self.post(self.author, '/api/videos/uploads/' + ident + '/parts', {'part_number': 1})
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(self.row(ident)['operation_token'])

    def test_finalized_storage_retry_does_not_complete_multipart_twice(self):
        ident = self.begin(); original = self.store.head
        with patch.object(v.storage, 'head', side_effect=RuntimeError('temporary outage')):
            self.assertEqual(self.post(self.author, '/api/videos/uploads/' + ident + '/complete').status_code, 503)
        self.assertTrue(self.row(ident)['storage_completed_at'])
        self.finish(ident)
        self.assertEqual(sum(call[0] == 'complete' for call in self.store.calls), 1)
        self.assertIsNotNone(original(self.row(ident)['object_key']))

    def test_lost_completion_response_recovers_actual_object(self):
        ident = self.begin(); original = self.store.complete
        def lost(*args):
            original(*args); raise RuntimeError('response lost')
        with patch.object(v.storage, 'complete', side_effect=lost):
            self.assertEqual(self.post(self.author, '/api/videos/uploads/' + ident + '/complete').status_code, 503)
        self.assertFalse(self.row(ident)['storage_completed_at'])
        self.finish(ident)
        self.assertEqual(sum(call[0] == 'complete' for call in self.store.calls), 1)

    def test_delete_revokes_first_and_keeps_failed_cleanup_retryable(self):
        ident = self.begin(); self.finish(ident); self.approve(ident)
        self.assertEqual(self.post(self.other, '/api/videos/' + ident + '/delete').status_code, 404)
        with patch.object(v.storage, 'delete', side_effect=RuntimeError('temporary outage')):
            response = self.post(self.author, '/api/videos/' + ident + '/delete')
        self.assertEqual(response.status_code, 200); self.assertFalse(response.json['storage_deleted'])
        self.assertEqual(self.guest.get('/api/videos/' + ident + '/play').status_code, 404)
        pending = self.author.get('/api/videos/me').json['videos']
        self.assertEqual(pending[0]['id'], ident); self.assertTrue(pending[0]['storage_cleanup_pending'])
        response = self.post(self.author, '/api/videos/' + ident + '/delete')
        self.assertTrue(response.json['storage_deleted'])
        self.assertEqual(self.author.get('/api/videos/me').json['total'], 0)
        with self.app.app_context(), m.database() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM community_video_reviews WHERE video_id=? AND new_state='deleted'", (ident,)).fetchone()['n'], 1)

    def test_report_is_private_deduplicated_and_does_not_automatically_hide_video(self):
        ident = self.begin(); self.finish(ident); self.approve(ident)
        for _ in range(2):
            self.assertEqual(self.post(self.other, '/api/videos/' + ident + '/report', {'reason': 'Revisar los permisos de esta canción.'}).status_code, 200)
        queue = self.admin.get('/api/admin/videos?state=published').json['videos']
        self.assertEqual(queue[0]['report_count'], 1)
        self.assertNotIn(self.other_id, str(queue))
        self.assertEqual(self.guest.get('/api/videos').json['total'], 1)
        self.assertEqual(self.guest.get('/api/videos/' + ident + '/play').status_code, 302)

    def test_archived_creator_is_not_public_or_previewable(self):
        ident = self.begin(); self.finish(ident); self.approve(ident)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO member_archives VALUES(?,?,?,?,NULL)', (self.owner_id, m.stamp(m.now_utc()), None, 'Test archive'))
        self.assertEqual(self.guest.get('/api/videos').json['total'], 0)
        self.assertEqual(self.guest.get('/api/videos/' + ident + '/play').status_code, 404)
        self.assertEqual(self.admin.get('/api/admin/videos/' + ident + '/preview').status_code, 404)
        self.assertEqual(self.post(self.admin, '/api/admin/videos/' + ident + '/review', {'decision': 'approve', 'review_confirmed': True}).status_code, 409)

    def test_delete_during_completion_never_resurrects_content(self):
        ident = self.begin(); original = self.store.complete
        def completing(*args):
            result = original(*args)
            self.assertEqual(self.post(self.author, '/api/videos/' + ident + '/delete').status_code, 200)
            return result
        with patch.object(v.storage, 'complete', side_effect=completing):
            result = self.post(self.author, '/api/videos/uploads/' + ident + '/complete')
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.row(ident)['state'], 'deleted')
        self.assertEqual(self.guest.get('/api/videos').json['total'], 0)

    def test_delete_during_remote_start_preserves_failed_abort_for_retry(self):
        original = self.store.start
        created = {}
        def starting(key, mime):
            upload = original(key, mime); ident = key.split('/')[-2]
            created.update(id=ident, upload=upload)
            response = self.post(self.author, '/api/videos/' + ident + '/delete')
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json['storage_deleted'])
            return upload
        with patch.object(v.storage, 'start', side_effect=starting), patch.object(v.storage, 'abort', side_effect=RuntimeError('temporary abort failure')):
            response = self.post(self.author, '/api/videos/uploads', {'title': 'Vídeo', 'description': '', 'category': 'other', 'filename': 'video.mp4', 'size_bytes': len(MP4), 'mime_type': 'video/mp4', 'rights_confirmed': True})
        self.assertEqual(response.status_code, 409)
        row = self.row(created['id'])
        self.assertEqual(row['state'], 'deleted'); self.assertEqual(row['upload_id'], created['upload'])
        self.assertIsNone(row['storage_deleted_at'])
        self.assertTrue(self.author.get('/api/videos/me').json['videos'][0]['storage_cleanup_pending'])
        self.assertTrue(self.post(self.author, '/api/videos/' + created['id'] + '/delete').json['storage_deleted'])

    def test_late_remote_object_reopens_cleanup_if_its_delete_fails(self):
        ident = self.begin(); row = self.row(ident)
        def complete_after_cancel(key, upload_id, parts):
            response = self.post(self.author, '/api/videos/' + ident + '/delete')
            self.assertTrue(response.json['storage_deleted'])
            # The provider finishes a previously accepted completion after its
            # abort raced with cancellation. It remains private in every state.
            self.store.objects[key] = {'ContentLength': len(MP4), 'ContentType': 'video/mp4', 'ETag': '"late-object"', 'body': MP4}
            return 'late-object'
        calls = []
        def deleting(key):
            calls.append(key)
            if len(calls) > 1:
                raise RuntimeError('late cleanup unavailable')
            self.store.delete(key)
        with patch.object(v.storage, 'complete', side_effect=complete_after_cancel), patch.object(v.storage, 'delete', side_effect=deleting):
            response = self.post(self.author, '/api/videos/uploads/' + ident + '/complete')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.row(ident)['state'], 'deleted')
        self.assertIsNone(self.row(ident)['storage_deleted_at'])
        self.assertTrue(self.row(ident)['storage_completed_at'])
        self.assertEqual(self.guest.get('/api/videos/' + ident + '/play').status_code, 404)
        self.assertTrue(self.post(self.author, '/api/videos/' + ident + '/delete').json['storage_deleted'])

    def test_stale_delete_cannot_confirm_a_later_object_was_removed(self):
        ident = self.begin(); row = self.row(ident)
        original = self.store.delete
        def late_completion(key):
            original(key)
            # The storage DELETE finishes before a previously accepted remote
            # completion materializes. Its worker records a newer pending
            # cleanup before this request can confirm its earlier deletion.
            self.store.objects[key] = {'ContentLength': len(MP4), 'ContentType': 'video/mp4',
                                       'ETag': '"late-object"', 'body': MP4}
            with self.app.app_context(), m.database() as conn:
                conn.execute("UPDATE community_videos SET storage_completed_at=?,storage_deleted_at=NULL,revision=revision+1 WHERE id=? AND state='deleted'",
                             (m.stamp(m.now_utc()), ident))
        with patch.object(v.storage, 'delete', side_effect=late_completion):
            response = self.post(self.author, '/api/videos/' + ident + '/delete')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['storage_deleted'])
        self.assertIsNone(self.row(ident)['storage_deleted_at'])
        self.assertIn(row['object_key'], self.store.objects)
        self.assertTrue(self.author.get('/api/videos/me').json['videos'][0]['storage_cleanup_pending'])
        self.assertEqual(self.guest.get('/api/videos/' + ident + '/play').status_code, 404)
        self.assertTrue(self.post(self.author, '/api/videos/' + ident + '/delete').json['storage_deleted'])
        self.assertNotIn(row['object_key'], self.store.objects)


if __name__ == '__main__':
    unittest.main()
