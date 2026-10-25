import os

BASE_URL = os.getenv('MAGGY_TEST_BASE_URL', 'http://127.0.0.1:8080')


def login_context(context):
    username=os.environ.get('MAGGY_TEST_USER')
    password=os.environ.get('MAGGY_TEST_PASSWORD')
    if not username or not password:
        raise RuntimeError('Ejecuta las pruebas mediante tests/run_browsers.py (servidor y usuarios aislados).')
    response=context.request.get(BASE_URL+'/api/account/me')
    csrf=response.json()['csrf']
    result=context.request.post(BASE_URL+'/api/account/login',data={'username':username,'password':password},headers={'X-CSRF-Token':csrf})
    assert result.status==200, 'Test login failed'

    return context.request.get(BASE_URL+'/api/account/me').json()['user']
