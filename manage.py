"""Local administration. Passwords are never CLI arguments or logged."""
import argparse
import getpass
from storage import INTEGRITY_ERRORS
from app import app
from membership import clean_username, create_admin, database, validate_password
from werkzeug.security import generate_password_hash

parser = argparse.ArgumentParser()
parser.add_argument('command', choices=['create-admin', 'set-password'])
parser.add_argument('--username', default='admin')
args = parser.parse_args()
password = getpass.getpass('Nueva contraseña (mínimo 12 caracteres): ')
if password != getpass.getpass('Repite la contraseña: '):
    raise SystemExit('Las contraseñas no coinciden.')
try:
    with app.app_context():
        if args.command == 'create-admin':
            create_admin(args.username, password)
        else:
            validate_password(password)
            with database() as conn:
                result = conn.execute('UPDATE members SET password_hash=?,session_version=session_version+1 WHERE username=?', (generate_password_hash(password), clean_username(args.username)))
                if not result.rowcount:
                    raise ValueError('La cuenta no existe.')
    print('Cuenta actualizada. Ya puedes iniciar sesión desde /account en cualquier dispositivo.')
except (ValueError,) + INTEGRITY_ERRORS as exc:
    raise SystemExit(str(exc))
