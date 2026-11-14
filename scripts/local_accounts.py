"""Local multi-shop account credentials and role bindings."""
import argparse
from contextlib import closing
import getpass
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3


ACCOUNT = re.compile(r'[a-z0-9][a-z0-9_-]{0,39}')
ROLES = ('viewer', 'operator', 'admin')
ITERATIONS = 600_000


class AccountError(ValueError):
    pass


def _account(value):
    if not isinstance(value, str) or ACCOUNT.fullmatch(value) is None:
        raise AccountError('账号编号无效')
    return value


def _shop(value):
    if not isinstance(value, str) or ACCOUNT.fullmatch(value) is None:
        raise AccountError('店铺编号无效')
    return value


def _password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128 or value.isspace():
        raise AccountError('密码必须为12至128个字符')
    return value


class LocalAccountStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS accounts(
                    account_id TEXT PRIMARY KEY,
                    salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    iterations INTEGER NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)),
                    revision INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS account_roles(
                    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
                    shop_id TEXT NOT NULL,
                    access_role TEXT NOT NULL CHECK(access_role IN ('viewer','operator','admin')),
                    PRIMARY KEY(account_id, shop_id)
                );
            ''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(accounts)')}
            if 'revision' not in columns:
                db.execute('ALTER TABLE accounts ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')

    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        return closing(db)

    def set_account(self, account_id, password, shop_id, access_role):
        account_id, password, shop_id = _account(account_id), _password(password), _shop(shop_id)
        if access_role not in ROLES:
            raise AccountError('账号角色无效')
        salt = secrets.token_bytes(32)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT INTO accounts(account_id,salt,password_hash,iterations,disabled,revision)
                          VALUES(?,?,?,?,0,1) ON CONFLICT(account_id) DO UPDATE SET
                          salt=excluded.salt,password_hash=excluded.password_hash,
                          iterations=excluded.iterations,disabled=0,revision=accounts.revision+1''',
                       (account_id, salt, digest, ITERATIONS))
            db.execute('''INSERT INTO account_roles(account_id,shop_id,access_role) VALUES(?,?,?)
                          ON CONFLICT(account_id,shop_id) DO UPDATE SET access_role=excluded.access_role''',
                       (account_id, shop_id, access_role))
            db.commit()
        return {'account_id': account_id, 'shop_id': shop_id, 'access_role': access_role}

    def set_disabled(self, account_id, disabled=True):
        account_id = _account(account_id)
        with self._db() as db:
            changed = db.execute('UPDATE accounts SET disabled=?,revision=revision+1 WHERE account_id=?',
                                 (bool(disabled), account_id)).rowcount
            db.commit()
        if changed != 1:
            raise AccountError('账号不存在')

    def authenticate(self, account_id, password, shop_id):
        # Keep the expensive work and public failure identical for missing and
        # invalid accounts, avoiding a cheap account-existence oracle.
        valid_id = isinstance(account_id, str) and ACCOUNT.fullmatch(account_id) is not None
        valid_password = isinstance(password, str) and 1 <= len(password) <= 128
        valid_shop = isinstance(shop_id, str) and ACCOUNT.fullmatch(shop_id) is not None
        row = None
        if valid_id and valid_shop:
            with self._db() as db:
                row = db.execute('''SELECT a.salt,a.password_hash,a.iterations,a.disabled,r.access_role,a.revision
                                    FROM accounts a LEFT JOIN account_roles r
                                    ON r.account_id=a.account_id AND r.shop_id=?
                                    WHERE a.account_id=?''', (shop_id, account_id)).fetchone()
        salt = row[0] if row else b'\0' * 32
        expected = row[1] if row else b'\0' * 32
        iterations = row[2] if row else ITERATIONS
        supplied = (password if valid_password else '').encode('utf-8')
        actual = hashlib.pbkdf2_hmac('sha256', supplied, salt, iterations)
        if (row is None or row[3] or row[4] is None or not valid_password
                or not hmac.compare_digest(actual, expected)):
            raise AccountError('账号、密码或店铺权限无效')
        return {'account_id': account_id, 'shop_id': shop_id, 'access_role': row[4],
                '_revision': row[5]}

    def validate_session(self, account_id, shop_id, revision):
        with self._db() as db:
            row = db.execute('''SELECT a.disabled,a.revision,r.access_role FROM accounts a
                                LEFT JOIN account_roles r ON r.account_id=a.account_id AND r.shop_id=?
                                WHERE a.account_id=?''', (shop_id, account_id)).fetchone()
        if row is None or row[0] or row[1] != revision or row[2] is None:
            return None
        return {'account_id': account_id, 'shop_id': shop_id, 'access_role': row[2],
                '_revision': row[1]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--account', required=True)
    parser.add_argument('--shop-id', required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    args = parser.parse_args(argv)
    first = getpass.getpass('新密码: ')
    second = getpass.getpass('再次输入: ')
    if first != second:
        parser.error('两次密码不一致')
    LocalAccountStore(args.database).set_account(args.account, first, args.shop_id, args.role)
    print('账号已保存；密码未输出。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
