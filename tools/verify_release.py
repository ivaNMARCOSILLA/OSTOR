"""Verify a distributable source archive, its manifest, and private-file exclusion."""
import argparse,hashlib,json
from pathlib import PurePosixPath
import zipfile
p=argparse.ArgumentParser();p.add_argument('archive');args=p.parse_args()
with zipfile.ZipFile(args.archive) as z:
 names=z.namelist();assert len(names)==len(set(names)),'Duplicate archive paths'
 assert z.testzip() is None,'Corrupt ZIP entry'
 for name in names:
  path=PurePosixPath(name)
  assert not path.is_absolute() and '..' not in path.parts and path.parts[0]=='Ol','Unsafe archive path'
  assert not any(part in {'.git','.instance','maggy-private','__pycache__','.env.local','.env.production'} for part in path.parts),'Private state included'
  assert path.name!='.env' and path.suffix not in {'.sqlite3','.db','.jks','.keystore','.pem','.p12'},'Private state or signing key included'
 manifest=z.read('Ol/MAGGY_SHA256.txt').decode();verified=set()
 for line in manifest.splitlines():
  digest,name=line.split('  ',1);assert hashlib.sha256(z.read('Ol/'+name)).hexdigest()==digest,'SHA-256 mismatch: '+name;verified.add('Ol/'+name)
 assert set(names)==verified|{'Ol/MAGGY_SHA256.txt'},'Unmanifested files'
 web=json.loads(z.read('Ol/manifest.webmanifest'));assert web['name'].startswith('Ol') and web['start_url']=='/'
 for key in ['Ol/app.py','Ol/payments.py','Ol/operations.py','Ol/assets/vendor/livekit-client-2.23.0.umd.js','Ol/android/twa-manifest.template.json']:
  assert key in verified,'Missing runtime or packaging component'
 print('Verified source ZIP:',len(verified),'files; SHA-256 matches; no private account data or signing keys.')
 print('Target: web/PWA source. Android template included; not a signed AAB or store publication.')
