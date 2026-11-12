from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import subprocess
import sys
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.product_store import Conflict, ProductError, ProductStore, product_prompt_info


class ProductStoreTests(unittest.TestCase):
    def test_business_csv_import_is_atomic_and_preserves_unknowns(self):
        product_id = self.product()['id']
        header = 'source,period_start,period_end,scope,clicks,orders,refunds,stock\n'
        first = '商家报表,2026-11-01,2026-11-01,"商品,按日",0,,,10\n'
        invalid = '第二来源,2026-11-02,2026-11-02,商品,-1,,,\n'
        with self.assertRaisesRegex(ProductError, '第 3 行'):
            self.store.import_business_metrics(product_id, header + first + invalid)
        self.assertEqual(self.store.business_metrics(product_id), [])
        self.assertEqual(self.store.import_business_metrics(product_id, '\ufeff' + header + first), 1)
        row, = self.store.business_metrics(product_id)
        self.assertEqual((row['clicks'], row['orders'], row['stock'], row['scope']), (0, None, 10, '商品,按日'))
        with self.assertRaisesRegex(ProductError, '重复'):
            self.store.import_business_metrics(product_id, header + first + first)

    def test_business_csv_count_limit_is_atomic(self):
        product_id = self.product()['id']
        header = 'source,period_start,period_end,scope,refunds\n'
        valid = f'商家报表,2026-11-01,2026-11-01,商品,{2**63-1}\n'
        overflow = f'商家报表,2026-11-02,2026-11-02,商品,{2**63}\n'
        with self.assertRaisesRegex(ProductError, '第 3 行.*退款超出'):
            self.store.import_business_metrics(product_id, header + valid + overflow)
        self.assertEqual(self.store.business_metrics(product_id), [])
        self.store.import_business_metrics(product_id, header + valid)
        row, = self.store.business_metrics(product_id)
        self.assertEqual(row['refunds'], 2**63-1)

    def test_business_metrics_preserve_unknowns_and_source_scope(self):
        product_id = self.product()['id']
        period = {'period_start': '2026-11-01', 'period_end': '2026-11-07', 'scope': '店铺商品，按报表时区'}
        self.store.save_business_metrics(product_id, source='商家报表', orders=0, **period)
        self.store.save_business_metrics(product_id, source='人工盘点', stock=12, **period)
        self.store.save_business_metrics(product_id, source='商家报表', orders=0, clicks=9, **period)
        records = {row['source']: row for row in ProductStore(self.store.path.parent).business_metrics(product_id)}
        self.assertEqual(len(records), 2)
        self.assertEqual(records['商家报表']['orders'], 0)
        self.assertEqual(records['商家报表']['clicks'], 9)
        self.assertIsNone(records['商家报表']['refunds'])
        self.assertIsNone(records['人工盘点']['orders'])
        self.assertEqual(records['人工盘点']['stock'], 12)
        with self.assertRaises(ProductError):
            self.store.save_business_metrics(product_id, source='商家报表', orders=True, **period)

    def test_live_control_revision_is_deduplicated(self):
        self.store.record_live_control('scene', 1, True, 102)
        self.store.record_live_control('scene', 1, True, 103)
        self.store.record_live_control('scene', 2, False, 104)
        with ProductStore(self.store.path.parent).connect() as db:
            rows = db.execute('SELECT revision, manual, occurred_at FROM live_control_events ORDER BY revision').fetchall()
        self.assertEqual([tuple(row) for row in rows], [(1, 1, 102), (2, 0, 104)])

    def test_live_session_terminal_record_survives_reopen_and_retry(self):
        self.store.record_live_session('scene', 100)
        self.store.record_live_session('scene', 100, started_at=102, status='running')
        running = self.store.live_session_record('scene')
        self.assertEqual(running['status'], 'running')
        self.assertEqual(running['started_at'], 102)
        self.assertIsNone(running['ended_at'])
        self.store.record_live_session('scene', 100, started_at=102, ended_at=110, status='stopped', frames=200)
        reopened = ProductStore(self.store.path.parent)
        reopened.record_live_session('scene', 100)
        with reopened.connect() as db:
            row = db.execute('SELECT * FROM live_sessions WHERE session_id=?', ('scene',)).fetchone()
        self.assertEqual(tuple(row), ('scene', 100, 102, 110, 'stopped', 200))

    def test_rotation_completion_is_durable_and_deduplicated(self):
        product = self.product()
        script = self.store.add_script(product, '商品口播')
        item = {'product_id': product['id'], 'product_version': product['version'], 'script_id': script}
        self.store.record_rotation_completion('session', 'task', item, 1, sample_start=960, sample_end=1920)
        self.store.record_rotation_completion('session', 'task', item, 1)
        with ProductStore(self.store.path.parent).connect() as db:
            rows = db.execute('SELECT * FROM live_rotation_events').fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['script_id'], script)
        self.assertEqual(rows[0]['product_version'], product['version'])
        self.assertEqual(rows[0]['segment_index'], 1)
        self.assertEqual((rows[0]['sample_start'], rows[0]['sample_end']), (960, 1920))
        self.assertTrue(rows[0]['completed_at'])
        reopened = ProductStore(self.store.path.parent)
        events = reopened.rotation_events('session')
        self.assertEqual([event['task_id'] for event in events], ['task'])
        self.assertEqual(reopened.rotation_events('session', after=events[0]['cursor']), [])
        self.assertEqual(reopened.rotation_events('another-session'), [])

    def test_selected_script_expires_with_its_product_facts(self):
        product = self.edit(self.product(), product_facts={
            'promotion': {'value': 'offer', 'status': 'verified', 'source': 'catalog',
                          'expires_at': '2026-11-12T00:00:00Z'},
        })
        script = self.store.add_script(product, '活动话术')
        with self.store.connect() as db:
            db.execute('UPDATE scripts SET created_at=? WHERE id=?',
                       ('2026-11-11T00:00:00.000Z', script))
        class Clock(datetime):
            current = datetime(2026, 11, 11, tzinfo=timezone.utc)

            @classmethod
            def now(cls, tz=None):
                return cls.current

        with patch('scripts.product_store.datetime', Clock):
            self.store.select_script(product['id'], script)
            self.assertEqual(self.store.selected_script(product['id']), script)
            Clock.current = datetime(2026, 11, 12, tzinfo=timezone.utc)
            self.assertIsNone(self.store.selected_script(product['id']))
            with self.assertRaises(Conflict):
                self.store.select_script(product['id'], script)
            prompt = product_prompt_info(product, now=datetime(2026, 11, 11, tzinfo=timezone.utc))
            with self.assertRaisesRegex(Conflict, '生成期间商品事实已到期'):
                self.store.add_script(product, '迟到的话术', source='llm', expected_prompt_info=prompt)
            self.assertEqual([row['id'] for row in self.store.scripts(product['id'])], [script])

    def test_versioned_product_prompt_filters_expired_and_unknown_facts(self):
        original = self.product()
        now = datetime(2026, 11, 11, tzinfo=timezone.utc)
        self.assertEqual(product_prompt_info(original, now=now)['content'], '容量300毫升')
        edited = self.edit(original, product_facts={
            'price': {'value': 100, 'status': 'verified', 'source': 'catalog'},
            'promotion': {'value': 'expired offer', 'status': 'verified',
                          'source': 'catalog', 'expires_at': '2026-11-11T00:00:00Z'},
            'stock': {'value': 10, 'status': 'unknown', 'source': 'catalog'},
        })
        current = self.store.get(edited['id'])
        self.assertEqual(current['extra']['未知原字段'], original['extra']['未知原字段'])
        self.assertEqual(current['version'], original['version'] + 1)
        self.assertEqual(json.loads(product_prompt_info(current, now=now)['content']), {'price': 100})

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
