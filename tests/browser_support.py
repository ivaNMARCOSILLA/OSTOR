import os

BASE_URL = os.getenv('MAGGY_TEST_BASE_URL', 'http://127.0.0.1:8080')


# Playwright's built-in wait_for_function uses globalThis.eval in the page's main
# world. A strict production CSP correctly blocks that implementation. Poll using
# debugger function evaluation instead; never weaken or bypass the page's CSP.
def _csp_safe_wait_for_function(self, expression, *, arg=None, timeout=None, polling=None):
    import time
    from playwright.sync_api import Error, TimeoutError
    budget=self._impl_obj._timeout_settings.timeout(timeout)
    deadline=time.monotonic()+budget/1000 if budget else None
    interval=50 if polling in (None,'raf') else float(polling)
    if interval<=0:raise ValueError('Polling interval must be positive')
    predicate="arg => {const predicate=("+expression.strip().rstrip(';')+");return typeof predicate==='function'?predicate(arg):predicate;}"
    while True:
        handle=None
        try:
            handle=self.evaluate_handle(predicate,arg)
            if handle.evaluate('value=>Boolean(value)'):return handle
        except Error as error:
            if 'Execution context was destroyed' not in str(error):raise
        finally:
            if handle is not None:
                try:
                    if not handle.evaluate('value=>Boolean(value)'):handle.dispose()
                except Error:pass
        if deadline is not None and time.monotonic()>=deadline:
            raise TimeoutError(f'CSP-safe predicate polling exceeded {budget} ms')
        self.wait_for_timeout(min(interval,50))

from playwright.sync_api import Page
Page.wait_for_function=_csp_safe_wait_for_function


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
