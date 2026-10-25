"""Vercel WSGI entrypoint: preserve paths for account, assets and API routes."""
from urllib.parse import urlsplit
from app import app as flask_app


class VercelPathAdapter:
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        uri = environ.get('REQUEST_URI', '')
        if uri.startswith('/') and not uri.startswith('//'):
            environ['PATH_INFO'] = urlsplit(uri).path
        return self.application(environ, start_response)


app = VercelPathAdapter(flask_app)
