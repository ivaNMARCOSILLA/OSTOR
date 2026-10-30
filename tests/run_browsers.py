"""Run functional checks against a temporary database, never real paid accounts."""
import os
import json,hashlib
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def run():
    selected=sys.argv[1:] or ['test_preview_browser.py','test_audio_browser.py','test_membership_browser.py','test_streamers_browser.py']
    # Suites must not inherit other suites' accounts, invitations or rewards.
    if len(selected)>1:
        for name in selected:
            subprocess.run([sys.executable,str(Path(__file__).resolve()),name],cwd=ROOT,check=True)
        return
    with tempfile.TemporaryDirectory() as directory:
        os.environ.setdefault('OL_PAYMENT_PROVIDER','legacy_paypal')
        os.environ.setdefault('OL_LIVE_PREMIERE','0')
        os.environ.pop('DATABASE_URL', None)
        os.environ.pop('VERCEL', None)
        os.environ.pop('MAGGY_SESSION_SECRET', None)
        os.environ.pop('SECRET_KEY', None)
        os.environ['MAGGY_DATA_DIR']=directory
        os.environ['MAGGY_COOKIE_SECURE']='0'  # Loopback HTTP test server only.
        sys.path.insert(0,str(ROOT))
        code=patch('human_check.new_code',return_value='OL234');code.start()
        from app import app
        # Existing regression suites deliberately exercise the Spanish interface.
        # Locale-specific browser tests supply their own language fixtures.
        if selected!=['test_site_language_browser.py'] and 'locale_preferences.preference' in app.view_functions:
            from flask import jsonify
            app.view_functions['locale_preferences.preference']=lambda:jsonify(language='es',source='isolated_test',supported=['es','ca','en','fr','pt','de','it'])
        import email_security
        mail_directory=Path(directory)/'mail';mail_directory.mkdir()
        def capture_mail(recipient,title,body):
            target=mail_directory/(hashlib.sha256(recipient.encode()).hexdigest()+'.jsonl')
            with target.open('a') as stream:stream.write(json.dumps({'recipient':recipient,'title':title,'body':body})+'\n')
        delivery_patch=patch.object(email_security,'deliver_to',side_effect=capture_mail);delivery_patch.start()
        mail_ready_patch=patch.object(email_security,'mail_ready',return_value=True);mail_ready_patch.start()
        stripe_fixture_patches=[]
        if selected==['test_annual_checkout_browser.py']:
            import payments,notifications
            from urllib.parse import urlencode
            def stripe_fixture(method,path,data=None,**kwargs):
                if method=='POST' and path=='/checkout/sessions':
                    assert data['mode']=='payment' and data['line_items[0][price_data][unit_amount]']=='2500'
                    assert data['metadata[annual_terms_version]']=='2026-10-29-v2'
                    checkout='cs_local_'+secrets.token_hex(8)
                    return {'id':checkout,'url':'https://checkout.stripe.com/c/pay/local-fixture?'+urlencode({'order':data['metadata[ol_order]'],'checkout':checkout})}
                if method=='GET' and path.startswith('/checkout/sessions/'):
                    return {'id':path.rsplit('/',1)[-1],'livemode':True,'payment_status':'unpaid'}
                raise AssertionError('Unexpected external Stripe operation: '+path)
            stripe_fixture_patches=[patch.dict(os.environ,{'OL_PAYMENT_PROVIDER':'stripe','OL_LIVE_PREMIERE':'0','STRIPE_WEBHOOK_SECRET':'whsec_browser_local_fixture'}),patch.object(payments,'ready',return_value=True),patch.object(payments,'stripe',side_effect=stripe_fixture),patch.object(notifications,'mail_ready',return_value=True),patch.object(notifications,'deliver_to',side_effect=capture_mail)]
            for fixture in stripe_fixture_patches:fixture.start()
        from membership import create_admin
        from werkzeug.serving import make_server, WSGIRequestHandler
        password=secrets.token_urlsafe(32)
        with app.app_context(): create_admin('browser-admin',password)
        class QuietHandler(WSGIRequestHandler):
            def log_request(self,*args,**kwargs): pass
        server=make_server('127.0.0.1',0,app,threaded=True,request_handler=QuietHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        child_env=dict(os.environ,MAGGY_TEST_BASE_URL=f'http://127.0.0.1:{server.server_port}',MAGGY_TEST_USER='browser-admin',MAGGY_TEST_PASSWORD=password,OL_TEST_MAIL_CAPTURE_DIR=str(mail_directory))
        try:
            for name in selected:
                subprocess.run([sys.executable,str(ROOT/'tests'/name)],cwd=ROOT,env=child_env,check=True)
        finally:
            server.shutdown();server.server_close();delivery_patch.stop();mail_ready_patch.stop()
            for fixture in reversed(stripe_fixture_patches):fixture.stop()


if __name__=='__main__':run()
