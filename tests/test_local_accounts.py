from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts.local_accounts import AccountError, ITERATIONS, LocalAccountStore


class LocalAccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'accounts.sqlite3'
        self.store = LocalAccountStore(self.path)

    def test_password_is_hashed_and_role_is_bound_to_shop(self):
        result = self.store.set_account('alice', 'correct horse battery', 'shop-a', 'operator')
        self.assertEqual(result['access_role'], 'operator')
        authenticated = self.store.authenticate('alice', 'correct horse battery', 'shop-a')
        self.assertEqual({key: authenticated[key] for key in result}, result)
        with sqlite3.connect(self.path) as db:
            salt, digest, iterations = db.execute(
                'SELECT salt,password_hash,iterations FROM accounts WHERE account_id=?', ('alice',)).fetchone()
        self.assertEqual((len(salt), len(digest), iterations), (32, 32, ITERATIONS))
        self.assertNotIn(b'correct horse battery', self.path.read_bytes())
        with self.assertRaisesRegex(AccountError, '账号、密码或店铺权限无效'):
            self.store.authenticate('alice', 'correct horse battery', 'shop-b')

    def test_password_change_disable_and_failure_are_atomic(self):
        self.store.set_account('alice', 'first password value', 'shop-a', 'viewer')
        self.store.set_account('alice', 'second password value', 'shop-a', 'admin')
        with self.assertRaises(AccountError):
            self.store.authenticate('alice', 'first password value', 'shop-a')
        session = self.store.authenticate('alice', 'second password value', 'shop-a')
        self.assertEqual(session['access_role'], 'admin')
        self.store.set_disabled('alice')
        self.assertIsNone(self.store.validate_session('alice', 'shop-a', session['_revision']))
        with self.assertRaisesRegex(AccountError, '账号、密码或店铺权限无效'):
            self.store.authenticate('alice', 'second password value', 'shop-a')

    def test_invalid_inputs_and_unknown_account_share_public_failure(self):
        for args in (('Bad Account', 'long enough password', 'shop-a', 'admin'),
                     ('alice', 'short', 'shop-a', 'admin'),
                     ('alice', 'long enough password', '../shop', 'admin')):
            with self.subTest(args=args), self.assertRaises(AccountError):
                self.store.set_account(*args)
        messages = []
        for account, password in (('missing', 'some password value'), ('bad id', 'x')):
            with self.assertRaises(AccountError) as raised:
                self.store.authenticate(account, password, 'shop-a')
            messages.append(str(raised.exception))
        self.assertEqual(messages, ['账号、密码或店铺权限无效'] * 2)


if __name__ == '__main__':
    unittest.main()
