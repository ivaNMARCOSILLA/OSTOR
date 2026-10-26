"""Pruebas de funciones puras sin tocar la red ni requerir Flask.
Edición: Iván Marcos Illa · ELECTRONICAMA PRO 7.0.
Ejecutar: python -m unittest discover -s tests -p 'test_core.py' -v
"""
import ast
import importlib.util
import ipaddress
import re
import unittest
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

SOURCE = Path(__file__).resolve().parents[1] / 'app.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
NAMES = {'normalize', 'sanitize_query', 'relevance', 'allowed_stream_url'}
FUNCTIONS = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
namespace = {'re': re, 'unicodedata': unicodedata, 'urlparse': urlparse, 'ipaddress': ipaddress, 'MAX_SEARCH_LENGTH': 90, 'AUDIUS_STORAGE_HOST': 'validator.eeba4a6ca56a0d87af802270217c2a51.r2.cloudflarestorage.com'}
exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), str(SOURCE), 'exec'), namespace)


class TestCore(unittest.TestCase):
    def test_accent_normalization(self):
        self.assertEqual(namespace['normalize']('MÚSICA Electrónica!'), 'musica electronica')

    def test_search_string_bounded(self):
        self.assertEqual(namespace['sanitize_query']('   Melendi   canciones  '), 'Melendi canciones')
        self.assertEqual(len(namespace['sanitize_query']('x' * 200)), 90)

    def test_relevance_ranks_matching_song(self):
        matching = {'title': 'Melendi - Caminando por la vida', 'channel': 'Melendi', 'source': 'YOUTUBE'}
        unrelated = {'title': 'Ocean waves nature sounds', 'channel': 'Random', 'source': 'ARCHIVE'}
        self.assertGreater(namespace['relevance'](matching, 'melendi'), 0)
        self.assertLess(namespace['relevance'](unrelated, 'melendi'), 0)

    def test_stream_proxy_allowlist(self):
        allowed = namespace['allowed_stream_url']
        self.assertTrue(allowed('https://archive.org/download/record/file.mp3'))
        self.assertTrue(allowed('https://ia800234.us.archive.org/download/file.mp3'))
        self.assertTrue(allowed('https://discoveryprovider.audius.co/v1/tracks/1/stream'))
        for url in [
            'http://archive.org/', 'https://archive.org.evil.test/file',
            'https://127.0.0.1/secret', 'https://localhost/admin',
            'https://archive.org:444/file', 'https://example.com/audio.mp3',
            'https://user:pass@archive.org/file', 'file:///etc/passwd',
        ]:
            self.assertFalse(allowed(url), url)


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(importlib.util.find_spec("flask"), "Flask no disponible en el entorno de verificación")
class LegalDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location('electronicama_legal_test_app', SOURCE)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
    def test_legal_pages_exist(self):
        for name in ('cookies.html', 'privacidad.html', 'aviso-legal.html'):
            response = self.module.app.test_client().get('/legal/' + name)
            self.assertEqual(response.status_code, 200, name)
            self.assertIn('Documento provisional', response.get_data(as_text=True))

    def test_block_path_traversal(self):
        self.assertEqual(self.module.app.test_client().get('/legal/../app.py').status_code, 404)


class LegalStructureStaticTests(unittest.TestCase):
    def test_legal_files_and_links(self):
        base = SOURCE.parent
        for filename in ('cookies.html', 'privacidad.html', 'aviso-legal.html'):
            self.assertTrue((base / 'legal' / filename).exists())
            self.assertIn('/legal/' + filename, (base / 'index.html').read_text('utf-8'))
        js = (base / 'assets' / 'app.js').read_text('utf-8')
        self.assertIn('cookie-settings', js)
        self.assertNotIn('googletagmanager.com/gtag/js', js)
