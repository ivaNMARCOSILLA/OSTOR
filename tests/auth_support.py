import tempfile
from pathlib import Path
from membership import create_admin, init_database


def authenticated_client(app, cleanup):
    from unittest.mock import patch
    legacy=patch.dict('os.environ',{'OL_PAYMENT_PROVIDER':'legacy_paypal'});legacy.start();cleanup(legacy.stop)
    temporary = tempfile.TemporaryDirectory()
    original = app.config['MEMBERSHIP_DATABASE']
    original_url = app.config.get('MEMBERSHIP_DATABASE_URL')
    app.config['MEMBERSHIP_DATABASE_URL'] = None
    cleanup(lambda: app.config.update(MEMBERSHIP_DATABASE_URL=original_url))
    app.config['MEMBERSHIP_DATABASE'] = str(Path(temporary.name) / 'test.sqlite3')
    cleanup(lambda: app.config.update(MEMBERSHIP_DATABASE=original))
    cleanup(temporary.cleanup)
    with app.app_context():
        init_database()
        create_admin('test-admin', 'test-password-only-123')
        from membership import database
        with database() as conn:
            user = conn.execute('SELECT * FROM members WHERE username=?', ('test-admin',)).fetchone()
    client = app.test_client()
    token = client.get('/api/account/me').json['csrf']
    client.post('/api/account/login', json={'username':'test-admin','password':'test-password-only-123'}, headers={'X-CSRF-Token':token})
    token = client.get('/api/account/me').json['csrf']
    original_post = client.post
    def post(*args, **kwargs):
        kwargs['headers'] = dict(kwargs.get('headers', {})) | {'X-CSRF-Token':token}
        return original_post(*args, **kwargs)
    client.post = post
    return client
