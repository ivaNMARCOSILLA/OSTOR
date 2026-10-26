import tempfile,unittest
from pathlib import Path
from tools.check_navigation import Document,inspect_source

class NavigationHealthTests(unittest.TestCase):
 def test_real_site_routes_assets_and_fragment_targets_are_consistent(self):
  report=inspect_source();self.assertEqual(report['errors'],[]);self.assertGreater(report['links'],100)
 def test_monitor_identifies_missing_target_asset_and_duplicate_id(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'assets').mkdir()
   for name in ['account.js','streamers.js','operations.js','navigation.js']:(root/'assets'/name).write_text('')
   (root/'index.html').write_text('<h1 id="same">A</h1><div id="same"></div><a href="/account#missing">Entrar</a><script src="/assets/missing.js"></script>')
   (root/'account.html').write_text('<form id="register-form"></form>')
   errors=inspect_source(root,{'/':'index.html','/account':'account.html'})['errors']
   self.assertTrue(any('duplicado' in x for x in errors));self.assertTrue(any('/account#missing' in x for x in errors));self.assertTrue(any('/assets/missing.js' in x for x in errors))
 def test_external_commercial_links_are_not_visited_by_source_checker(self):
  doc=Document('<a href="https://example.com">Fuera</a><button type="submit">Pagar</button>')
  self.assertEqual(doc.links,['https://example.com']);self.assertEqual(doc.ids,set())
