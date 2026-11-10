from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import sqlite3
from pathlib import Path
import tempfile
import unittest

from scripts.product_store import Conflict, ProductError, ProductStore


class ProductStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ProductStore(self.directory.name)

    def product(self, index=8):
        return self.store.save(title='测试茶杯', content='容量300毫升', product_index=index,
                               extra={'未知原字段': {'enabled': True}})

    def edit(self, p, **updates):
        args = dict(title=p['title'], content=p['content'], product_index=p['product_index'],
                    product_id=p['id'], version=p['version'])
        return self.store.save(**{**args, **updates})

    def test_sparse_indices_unicode_unknown_fields_and_process_reopen(self):
        a, b = self.product('008'), self.product(3)
        self.store.select(b['id'])
        script_id = self.store.add_script(a, '这款茶杯容量为300毫升。')
        code = ('from scripts.product_store import ProductStore; import sys,json; '
                's=ProductStore(sys.argv[1]); print(json.dumps([s.list(),s.selected(),s.scripts(sys.argv[2])],ensure_ascii=False))')
        result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code, self.directory.name, a['id']],
                                capture_output=True, text=True, encoding='utf-8', timeout=10, check=True)
        products, selected, scripts = json.loads(result.stdout)
        self.assertEqual(products, [a, b])
        self.assertEqual(selected, b['id'])
        self.assertEqual(scripts[0]['id'], script_id)
        self.assertEqual(scripts[0]['snapshot'], a)

    def test_duplicate_numeric_identity_rejected(self):
        self.product('008')
        with self.assertRaises(Conflict): self.product(8)
        self.assertEqual(len(self.store.list()), 1)

    def test_empty_invalid_and_bool_inputs_rejected(self):
        for updates in ({'title':''}, {'content':' '}, {'product_index':True},
                        {'product_index':1.5}, {'product_index':'abc'}, {'product_index':2**64}):
            with self.assertRaises(ProductError):
                self.store.save(**{**dict(title='茶杯', content='300毫升', product_index=1), **updates})
        self.assertEqual(self.store.list(), [])

    def test_concurrent_edit_only_one_wins(self):
        p = self.product()
        def attempt(i):
            try: return self.edit(p, content='内容%s' % i)
            except Conflict: return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(x is not None for x in results), 1)
        self.assertEqual(self.store.get(p['id'])['version'], 2)
        self.assertEqual(self.store.get(p['id'])['extra'], p['extra'])

    def test_stale_generation_does_not_overwrite_or_attach(self):
        p = self.product()
        first = self.store.add_script(p, '原话术', 'llm')
        self.edit(p, content='容量500毫升')
        with self.assertRaises(Conflict): self.store.add_script(p, '迟到的300毫升话术', 'llm')
        self.assertEqual([s['id'] for s in self.store.scripts(p['id'])], [first])

    def test_cross_product_snapshot_and_selection(self):
        a, b = self.product(8), self.product(3)
        with self.assertRaises(Conflict): self.store.add_script({**a, 'id': b['id']}, '串商品内容')
        self.store.add_script(a, '商品8的话术')
        self.assertEqual(self.store.scripts(b['id']), [])
        with self.assertRaises(ProductError): self.store.select('missing')
        self.assertIsNone(self.store.selected())

    def test_invalid_script_and_failed_update_leave_previous_data(self):
        a, b = self.product(8), self.product(3)
        with self.assertRaises(Conflict): self.edit(a, product_index=3)
        self.assertEqual(self.store.get(a['id']), a)
        for script in ('', ' ', None):
            with self.assertRaises(ProductError): self.store.add_script(a, script)
        self.assertEqual(self.store.scripts(a['id']), [])

    def test_revision_keeps_original_and_rejects_cross_product_parent(self):
        a,b=self.product(8),self.product(3)
        original=self.store.add_script(a,'原始300毫升话术',source='llm')
        current=self.edit(a,content='容量500毫升')
        edited=self.store.add_script(current,'修改为500毫升话术',parent_script_id=original)
        records=self.store.scripts(a['id'])
        self.assertEqual([r['product_version'] for r in records],[1,2])
        self.assertEqual(records[0]['text'],'原始300毫升话术')
        self.assertEqual(records[1]['parent_script_id'],original)
        self.assertEqual(records[1]['id'],edited)
        with self.assertRaises(ProductError): self.store.add_script(b,'不应跨商品',parent_script_id=original)
        self.assertEqual(self.store.scripts(b['id']),[])

    def test_version_one_database_migrates_without_losing_old_script(self):
        directory=Path(self.directory.name)/'old'
        directory.mkdir()
        path=directory/'products.sqlite3'
        a=self.product()
        with sqlite3.connect(path) as db:
            db.executescript('''CREATE TABLE products(id TEXT PRIMARY KEY,product_index INTEGER UNIQUE,
                legacy_index TEXT,title TEXT,content TEXT,extra TEXT,version INTEGER);
                CREATE TABLE scripts(id TEXT PRIMARY KEY,product_id TEXT REFERENCES products(id),
                product_version INTEGER,snapshot TEXT,text TEXT,source TEXT,created_at TEXT);
                PRAGMA user_version=1;''')
            db.execute('INSERT INTO products VALUES(?,?,?,?,?,?,?)',
                       (a['id'],8,json.dumps(a['product_index']),a['title'],a['content'],json.dumps(a['extra']),1))
            db.execute('INSERT INTO scripts VALUES(?,?,?,?,?,?,?)',('old-script',a['id'],1,json.dumps(a),'旧话术','llm','2026-11-10'))
        migrated=ProductStore(directory)
        self.assertEqual(migrated.get(a['id']),a)
        record=migrated.scripts(a['id'])[0]
        self.assertEqual(record['text'],'旧话术')
        self.assertIsNone(record['parent_script_id'])
        migrated.add_script(a,'从旧话术修改保存',parent_script_id='old-script')
        self.assertEqual(len(ProductStore(directory).scripts(a['id'])),2)

    def test_script_selection_persists_and_product_edits_invalidate(self):
        a,b=self.product(8),self.product(3)
        script=self.store.add_script(a,'商品8当前稿')
        self.store.select_script(a['id'],script)
        self.assertEqual(ProductStore(self.directory.name).selected_script(a['id']),script)
        with self.assertRaises(ProductError): self.store.select_script(b['id'],script)
        self.assertIsNone(self.store.selected_script(b['id']))
        changed=self.edit(a,content='更新商品信息')
        self.assertIsNone(self.store.selected_script(a['id']))
        with self.assertRaises(Conflict): self.store.select_script(a['id'],script)
        revised=self.store.add_script(changed,'更新后话术',parent_script_id=script)
        self.store.select_script(a['id'],revised)
        self.assertEqual(self.store.selected_script(a['id']),revised)


if __name__ == '__main__':
    unittest.main()
