import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from werkzeug.test import Client
from werkzeug.wrappers import Response
import membership
from api.index import app as vercel_app


class VercelConfigurationTests(unittest.TestCase):
    def test_vercel_never_falls_back_to_ephemeral_sqlite(self):
        with tempfile.TemporaryDirectory() as folder:
            state=str(Path(folder)/'must-not-be-created')
            with patch.dict(os.environ,{'VERCEL':'1','MAGGY_DATA_DIR':state},clear=True):
                with self.assertRaisesRegex(RuntimeError,'DATABASE_URL'):
                    membership.install(Flask('no-database'))
            self.assertFalse(Path(state).exists())

    def test_vercel_requires_a_stable_session_secret(self):
        with patch.dict(os.environ,{'VERCEL':'1','DATABASE_URL':'postgresql://localhost/test'},clear=True):
            with self.assertRaisesRegex(RuntimeError,'MAGGY_SESSION_SECRET'):
                membership.install(Flask('no-secret'))

    def test_rewritten_account_and_root_paths_are_preserved(self):
        client=Client(vercel_app,Response)
        with client.get('/api/index.py',environ_overrides={'REQUEST_URI':'/account'}) as response:
            self.assertEqual(response.status_code,200)
            self.assertIn('Iniciar sesión',response.get_data(as_text=True))
        with client.get('/api/index.py',environ_overrides={'REQUEST_URI':'/'}) as response:
            self.assertEqual(response.status_code,200)
            self.assertIn('preview-banner',response.get_data(as_text=True))
