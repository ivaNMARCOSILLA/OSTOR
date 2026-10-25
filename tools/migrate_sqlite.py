"""Copy an existing local Maggy database into an EMPTY PostgreSQL installation."""
import argparse
import getpass
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
TABLES={
    'members':['id','username','password_hash','role','created_at','access_until','welcome_used','session_version'],
    'payments':['id','member_id','plan','amount_cents','starts_at','ends_at','verified_at','verified_by','reference'],
    'invitations':['token_hash','member_id','expires_at','used_at'],
    'login_attempts':['bucket','attempted_at'],
}


def migrate(source,app):
    from membership import database
    path=Path(source).resolve()
    if not path.is_file():raise ValueError('No existe la base SQLite de origen.')
    if not app.config.get('MEMBERSHIP_DATABASE_URL'):raise ValueError('El destino debe ser PostgreSQL mediante DATABASE_URL.')
    original=sqlite3.connect('file:'+quote(str(path),safe='/\\:')+'?mode=ro',uri=True)
    original.row_factory=sqlite3.Row
    try:
        original.execute('BEGIN')
        rows={}
        for table,columns in TABLES.items():
            actual=[row['name'] for row in original.execute('PRAGMA table_info('+table+')')]
            if set(actual)!=set(columns):raise ValueError('La estructura SQLite no es compatible: '+table)
            rows[table]=[dict(row) for row in original.execute('SELECT '+','.join(columns)+' FROM '+table)]
        with app.app_context(),database() as connection:
            connection.execute('BEGIN IMMEDIATE')
            for table in TABLES:
                if connection.execute('SELECT COUNT(*) AS count FROM '+table).fetchone()['count']:
                    raise ValueError('El destino ya contiene datos. La migración no sobrescribe ni mezcla cuentas.')
            for table,columns in TABLES.items():
                query='INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')'
                for row in rows[table]:connection.execute(query,tuple(row[column] for column in columns))
        return {table:len(records) for table,records in rows.items()}
    finally:
        original.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True,help='Ruta local a .instance/members.sqlite3')
    args=parser.parse_args()
    if not os.environ.get('DATABASE_URL'):
        os.environ['DATABASE_URL']=getpass.getpass('Conexión PostgreSQL de destino (no se muestra): ')
    sys.path.insert(0,str(ROOT))
    try:
        from app import app
        result=migrate(args.source,app)
    except ValueError as error:
        raise SystemExit(str(error))
    except Exception as error:
        raise SystemExit('La migración no se completó ('+type(error).__name__+'). Revisa conexión y esquema; no se modificó la base de origen.')
    print('Migración completada:',', '.join(f'{name}: {count}' for name,count in result.items()))


if __name__=='__main__':main()
