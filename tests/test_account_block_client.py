"""Browser-independent checks of client behavior after a server account block."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AccountBlockClientTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the client behavior check')
    def test_existing_page_leaves_only_for_authoritative_account_block(self):
        result = subprocess.run(
            ['node', str(ROOT / 'tests/account_block_client_check.js'),
             str(ROOT / 'assets/account-block.js')],
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_guard_loads_before_other_page_scripts(self):
        for page in [ROOT / 'index.html', *(ROOT / 'assets').glob('*.html')]:
            with self.subTest(page=page.name):
                text = page.read_text()
                self.assertTrue(text[text.index('<head>') + len('<head>'):].startswith(
                    '<script defer src="/assets/account-block.js?v=9.31.1"></script>'))


if __name__ == '__main__':
    unittest.main()
