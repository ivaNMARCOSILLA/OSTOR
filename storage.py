"""Persistent PostgreSQL for Vercel; SQLite remains supported for local use."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

import certifi
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)
WRITE_LOCK = 17031989


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=()):
        if query.strip().upper() == 'BEGIN IMMEDIATE':
            # Preserve the serialized read/modify/write semantics used for
            # payments, invitation redemption and login throttling.
            return self.connection.execute('SELECT pg_advisory_xact_lock(%s)', (WRITE_LOCK,))
        query = query.replace('?', '%s').replace('MAX(welcome_used,', 'GREATEST(welcome_used,')
        return self.connection.execute(query, parameters)

    def executescript(self, script):
        # Application-owned schema only; never accept user-supplied SQL here.
        self.connection.execute('SELECT pg_advisory_xact_lock(%s)', (WRITE_LOCK,))
        self.connection.execute('CREATE SCHEMA IF NOT EXISTS maggy')
        for statement in script.split(';'):
            if statement.strip():
                self.connection.execute(statement)


def postgres_options(url):
    parsed = conninfo_to_dict(url)
    local = {'', 'localhost', '127.0.0.1', '::1'}
    hosts = set(parsed.get('host', '').split(','))
    addresses = set(parsed.get('hostaddr', '').split(','))
    if hosts <= local and addresses <= local:
        return {'sslmode': 'disable'}  # Loopback/local socket development only.
    return {'sslmode': 'verify-full', 'sslrootcert': os.getenv('MAGGY_DATABASE_CA') or certifi.where()}


@contextmanager
def open_database(config):
    url = config.get('MEMBERSHIP_DATABASE_URL')
    if url:
        try:
            connection = psycopg.connect(url, connect_timeout=10, row_factory=dict_row, **postgres_options(url))
        except (psycopg.Error, ValueError) as error:
            raise RuntimeError('No se pudo conectar con PostgreSQL. Revisa la configuración y TLS (' + type(error).__name__ + ').') from None
        try:
            connection.execute('SET LOCAL search_path TO maggy')
            connection.execute("SET LOCAL statement_timeout = '15000ms'")
            yield PostgresConnection(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    else:
        path = Path(config['MEMBERSHIP_DATABASE'])
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(path, timeout=15)
        os.chmod(path, 0o600)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
