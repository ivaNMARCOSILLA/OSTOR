"""Run functional checks against a temporary database, never real paid accounts."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]


def run():
    with tempfile.TemporaryDirectory() as directory:
        os.environ.pop('DATABASE_URL', None)
        os.environ.pop('VERCEL', None)
        os.environ.pop('MAGGY_SESSION_SECRET', None)
        os.environ.pop('SECRET_KEY', None)
        os.environ['MAGGY_DATA_DIR']=directory
        os.environ['MAGGY_COOKIE_SECURE']='0'  # Loopback HTTP test server only.
        sys.path.insert(0,str(ROOT))
        from app import app
        from membership import create_admin
        from werkzeug.serving import make_server, WSGIRequestHandler
        password=secrets.token_urlsafe(32)
        with app.app_context(): create_admin('browser-admin',password)
        class QuietHandler(WSGIRequestHandler):
            def log_request(self,*args,**kwargs): pass
        server=make_server('127.0.0.1',0,app,threaded=True,request_handler=QuietHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        child_env=dict(os.environ,MAGGY_TEST_BASE_URL=f'http://127.0.0.1:{server.server_port}',MAGGY_TEST_USER='browser-admin',MAGGY_TEST_PASSWORD=password)
        try:
            selected=sys.argv[1:] or ['test_preview_browser.py','test_audio_browser.py','test_membership_browser.py','test_streamers_browser.py']
            for name in selected:
                subprocess.run([sys.executable,str(ROOT/'tests'/name)],cwd=ROOT,env=child_env,check=True)
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__':run()
