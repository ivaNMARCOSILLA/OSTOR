"""Build a source ZIP from an explicit allowlist. Never package account state."""
import argparse
import ast
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
version=next(ast.literal_eval(n.value) for n in ast.parse((ROOT/'app.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets))
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=ROOT.parent/'artifacts'/('OL_'+version.replace('.','_')+'.zip'))
args = parser.parse_args()
root_files = ['.dockerignore','.env.example','.gitignore','.vercelignore','README.md','AUTORIA_MAGGY.md','Dockerfile','compose.yaml','app.py','membership.py','streamers.py','subscriptions.py','two_factor.py','operations.py','payments.py', 'moderation.py','community.py','notifications.py','rewards.py','founders.py','founder_slots.py','sounds.py','live_access.py','human_check.py','sticker_phrases.py','analytics.py','storage.py','manage.py','vercel.json','.python-version','index.html','manifest.webmanifest','sw.js','requirements.txt','requirements-dev.txt']
files = [ROOT/name for name in root_files]
for directory in ['api','assets','legal','tests','docs','tools','android']:
    for path in (ROOT/directory).rglob('*'):
        if not path.is_file(): continue
        relative=path.relative_to(ROOT)
        if any(part in {'__pycache__','archive','.instance','.git','.pytest_cache'} for part in relative.parts): continue
        if path.suffix in {'.pyc','.sqlite3','.zip'}: continue
        files.append(path)
files=sorted(set(files))
manifest=ROOT/'MAGGY_SHA256.txt'
manifest.write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT).as_posix()}\n' for path in files))
args.output.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in files+[manifest]: archive.write(path,Path('Ol')/path.relative_to(ROOT))
with zipfile.ZipFile(args.output) as archive:
    assert archive.testzip() is None
print(f'ZIP verificado: {args.output}; {len(files)} archivos con SHA-256. Estado de cuentas excluido.')
