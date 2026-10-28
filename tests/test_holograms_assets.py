import json,unittest
from pathlib import Path
import app
ROOT=Path(__file__).resolve().parents[1]
class HologramAssetTests(unittest.TestCase):
 def test_camera_is_allowed_on_home_without_microphone_and_wasm_type_is_usable(self):
  client=app.app.test_client()
  with client.get('/') as response:
   self.assertIn('camera=(self)',response.headers['Permissions-Policy']);self.assertIn('microphone=()',response.headers['Permissions-Policy'])
  with client.get('/assets/vendor/hands/hands_solution_wasm_bin.wasm') as response:
   self.assertEqual(response.status_code,200);self.assertIn('application/wasm',response.headers['Content-Type'])
 def test_large_assets_use_static_routing_and_api_catchall_remains_last(self):
  config=json.loads((ROOT/'vercel.json').read_text())
  self.assertIn({'src':'assets/**','use':'@vercel/static'},config['builds'])
  self.assertEqual(config['routes'][-1],{'src':'/(.*)','dest':'/api/index.py'})
  self.assertTrue(any(route.get('handle')=='filesystem' for route in config['routes'][:-1]))
  for path in ['hands.js','hands.binarypb','hand_landmark_lite.tflite','hands_solution_packed_assets.data','hands_solution_simd_wasm_bin.wasm','hands_solution_wasm_bin.wasm']:
   self.assertTrue((ROOT/'assets/vendor/hands'/path).is_file(),path)
