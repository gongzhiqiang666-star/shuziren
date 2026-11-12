import json
import subprocess
import sys
import os
import wave
import base64
from unittest.mock import patch
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.local_console import InstanceLock, create_server
from scripts.local_console_config import ConfigStore, shop_data_directory
from scripts.product_store import ProductStore


class ConsoleHTTPTests(unittest.TestCase):
    def test_workspace_traces_prepared_product_through_report_to_reusable_copy(self):
        store = ProductStore(self.directory.name)
        product = store.save(title='茶杯', content='商品说明', product_index=1, product_facts={
            '材质': {'status': 'verified', 'value': '陶瓷', 'source': '商品标签'},
        })
        product_id = product['id']
        script_id = store.add_script(product, '这是一只陶瓷杯。')
        store.select_script(product_id, script_id)
        preparation = '/api/live/preparation'
        self.assertEqual(self.call(preparation, {'product_ids': [product_id]})[0], 200)
        package = self.call(preparation + '/package')[1]
        self.assertEqual(package['items'][0]['selling_points'][0]['source'], '商品标签')
        revision = package['revision']
        self.assertEqual(self.call(preparation + '/review', {'revision': revision, 'review': '已核对'})[0], 200)
        rotation = self.call(preparation + '/rotation', {'revision': revision})[1]
        item, = rotation['items']
        self.assertEqual(item['script_id'], script_id)
        store.record_live_session('scene', 100, started_at=101, ended_at=110, status='stopped')
        store.record_rotation_completion('scene', 'spoken', item, 0, sample_start=0, sample_end=24000)
        report = self.call('/api/live/report?session_id=scene')[1]
        self.assertEqual(report['products'][0]['script_id'], script_id)
        status, response = self.call('/api/live/content-draft?session_id=scene&task_id=spoken')
        self.assertEqual(status, 200)
        draft = response['draft']
        self.assertEqual(draft['source']['product_version'], product['version'])
        self.assertEqual(draft['source']['script_id'], script_id)
        self.assertEqual(draft['narration'], '这是一只陶瓷杯。')

    def test_shop_workspaces_keep_product_and_metrics_data_isolated(self):
        first = ProductStore(shop_data_directory(self.directory.name, 'first'))
        second = ProductStore(shop_data_directory(self.directory.name, 'second'))
        product = first.save(title='茶杯', content='仅本店', product_index=1)
        first.save_business_metrics(product['id'], source='账单', scope='商品',
                                    period_start='2026-11-01', period_end='2026-11-01', orders=3)
        self.assertEqual(second.list(), [])
        self.assertEqual(ProductStore(self.directory.name).list(), [])
        self.assertEqual(first.business_metrics(product['id'])[0]['orders'], 3)
        with self.assertRaises(ValueError):
            shop_data_directory(self.directory.name, '../first')

    def test_shop_console_instances_isolate_write_tokens_and_catalogs(self):
        clients = []
        for shop_id in ('first', 'second'):
            config = ConfigStore(shop_data_directory(self.directory.name, shop_id))
            server = create_server(config, port=0)
            self.addCleanup(server.server_close)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            self.addCleanup(worker.join, 5)
            self.addCleanup(server.shutdown)
            client = ConsoleHTTPTests()
            client.base = f'http://127.0.0.1:{server.server_port}'
            client.token = client.call('/api/session')[1]['token']
            clients.append(client)
        first, second = clients
        payload = {'title': '茶杯', 'content': '仅本店', 'product_index': 1}
        self.assertEqual(first.call('/api/products', payload)[0], 200)
        self.assertEqual(second.call('/api/products', payload, **{'X-Console-Token': first.token})[0], 403)
        self.assertEqual(second.call('/api/products')[1]['products'], [])
        self.assertEqual(second.call('/api/products', {**payload, 'title': '桌布'})[0], 200)
        self.assertEqual([item['title'] for item in first.call('/api/products')[1]['products']], ['茶杯'])

    def test_promotion_spend_preserves_missing_attribution_and_corrects_bill(self):
        store = ProductStore(self.directory.name)
        product = store.save(title='茶杯', content='商品说明', product_index=1)
        route = '/api/promotion/spend'
        payload = {'product_id': product['id'], 'source': '商家账单', 'period_start': '2026-11-01',
                   'period_end': '2026-11-03', 'campaign': 'campaign-1', 'asset': 'clip-1', 'spend_minor': 0}
        self.assertEqual(self.call(route, payload), (200, {'records': [{**payload, 'attribution': None}]}))
        corrected = {**payload, 'spend_minor': 320, 'attribution': '账单记录窗口，订单归因未核对'}
        self.assertEqual(self.call(route, corrected)[0], 200)
        self.assertEqual(self.call(route + '?product_id=' + product['id']), (200, {'records': [corrected]}))
        self.assertEqual(self.call(route, {**payload, 'spend_minor': -1})[0], 400)
        preview_route = '/api/promotion/budget-preview'
        preview = {key: value for key, value in payload.items() if key != 'spend_minor'}
        self.assertEqual(self.call(preview_route, {**preview, 'asset': 'other', 'budget_minor': 500})[0], 400)
        status, result = self.call(preview_route, {**preview, 'budget_minor': 300})
        self.assertEqual(status, 200)
        self.assertEqual(result['preview'], {'bill': corrected, 'budget_minor': 300,
                                            'remaining_minor': -20, 'status': 'over_budget'})
        self.assertEqual(self.call(preview_route, {**preview, 'budget_minor': 320})[1]['preview']['status'], 'at_limit')
        plans = '/api/promotion/plans'
        plan = {**preview, 'budget_minor': 500, 'rationale': '验证新素材'}
        self.assertEqual(self.call(plans, {**plan, 'budget_minor': 300})[0], 409)
        status, result = self.call(plans, plan)
        self.assertEqual(status, 200)
        self.assertEqual(result['plan']['bill'], corrected)
        action = {'plan_id': result['plan']['id'], 'action': 'approved'}
        self.assertEqual(self.call(plans + '/action', action)[1]['plan']['status'], 'approved')
        self.assertEqual(self.call(route, corrected)[0], 200)
        self.assertEqual(self.call(plans + '?product_id=' + product['id'])[1]['plans'][0]['status'], 'approved')
        self.assertEqual(self.call(plans + '/action', action)[0], 200)
        self.assertEqual(self.call(route, {**corrected, 'spend_minor': 400})[0], 200)
        self.assertEqual(self.call(plans + '?product_id=' + product['id'])[1]['plans'][0]['status'], 'stale')
        self.assertEqual(self.call(plans + '/action', action)[0], 409)
        self.assertEqual(self.call(route, corrected)[0], 200)
        self.assertEqual(self.call(plans + '?product_id=' + product['id'])[1]['plans'][0]['status'], 'stale')
        self.assertEqual(self.call(plans + '/action', action)[0], 409)
        self.assertEqual(self.call(route, {**corrected, 'spend_minor': 400})[0], 200)
        self.assertEqual(self.call(plans + '/action', {**action, 'action': 'paused'})[1]['plan']['status'], 'paused')
        actions = self.call(plans + '/actions?plan_id=' + action['plan_id'])[1]['actions']
        self.assertEqual([entry['action'] for entry in actions], ['approved', 'paused'])
        self.assertEqual(self.call(plans + '?product_id=' + product['id']),
                         (200, {'plans': [{**result['plan'], 'status': 'paused'}]}))
        self.assertEqual(self.call(plans + '/action', action)[0], 409)
        status, replacement = self.call(plans, plan)
        self.assertEqual(status, 200)
        self.assertEqual(replacement['plan']['bill']['spend_minor'], 400)
        self.assertEqual(self.call(plans + '/action', {**action, 'plan_id': replacement['plan']['id']})[0], 200)
        comparison = {key: payload[key] for key in ('product_id', 'source', 'campaign', 'asset')}
        comparison.update(baseline_start='2026-11-01', baseline_end='2026-11-03',
                          trial_start='2026-11-04', trial_end='2026-11-06')
        compare_url = '/api/promotion/compare?' + urlencode(comparison)
        self.assertEqual(self.call(compare_url)[0], 400)
        self.assertEqual(self.call(route, {**payload, 'period_start': '2026-11-04',
                                           'period_end': '2026-11-06', 'spend_minor': 250})[0], 200)
        status, response = self.call(compare_url)
        self.assertEqual(status, 200)
        self.assertEqual(response['comparison']['spend_difference_minor'], -150)
        self.assertEqual(response['comparison']['conclusion'], 'uncertain')

    def test_sourcing_candidates_preserve_source_and_leave_missing_terms_unknown(self):
        route = '/api/sourcing/candidates'
        candidate = {'name': '陶瓷杯', 'supplier': '样品供应商', 'source': '商家报价单',
                     'observed_on': '2026-11-10', 'details': {'lead_time': '7天'}}
        self.assertEqual(self.call(route, {**candidate, 'observed_on': '2026-13-10'})[0], 400)
        self.assertEqual(self.call(route, {**candidate, 'details': {'unknown_field': '未知'}})[0], 400)
        status, result = self.call(route, candidate)
        self.assertEqual(status, 200)
        self.assertEqual(self.call(route), (200, {'candidates': [{'id': result['id'], **candidate}]}))
        trial_route = '/api/sourcing/trial'
        trial = {'candidate_id': result['id'], 'sample_evidence': '样品验收单 001',
                 'trial_evidence': '待开始试卖', 'cost_minor': 0, 'verdict': 'pending'}
        self.assertEqual(self.call(trial_route, {**trial, 'sample_evidence': ''})[0], 400)
        self.assertEqual(self.call(trial_route, {**trial, 'candidate_id': 'missing'})[0], 400)
        self.assertEqual(self.call(trial_route, trial), (200, {'trial': trial}))
        self.assertEqual(self.call(trial_route + '?candidate_id=' + result['id']), (200, {'trial': trial}))
        decision_route = '/api/sourcing/decision'
        decision = {'candidate_id': result['id'], 'decision': 'adopt', 'rationale': '样品与试卖已核对',
                    'constraints': '仅限已确认库存'}
        self.assertEqual(self.call(decision_route, decision)[0], 409)
        passed = {**trial, 'verdict': 'pass', 'trial_evidence': '试卖记录 001',
                  'metrics': {'orders': 5, 'refunds': 0, 'fulfilled_on_time': 4, 'gross_profit_minor': -100}}
        self.assertEqual(self.call(trial_route, {**passed, 'metrics': {'orders': 2, 'refunds': 3}})[0], 400)
        self.assertEqual(self.call(trial_route, {**passed, 'metrics': {'gross_profit_minor': True}})[0], 400)
        self.assertEqual(self.call(trial_route, passed)[0], 200)
        status, recorded = self.call(decision_route, decision)
        self.assertEqual(status, 200)
        self.assertEqual(recorded['decision']['trial'], passed)
        self.assertEqual(self.call(trial_route, trial)[0], 200)
        self.assertEqual(self.call(decision_route + '?candidate_id=' + result['id']), (200, recorded))

    def test_after_sales_comparison_keeps_unreported_categories_unknown(self):
        store = ProductStore(self.directory.name)
        product = store.save(title='茶杯', content='商品说明', product_index=1)
        query = {'product_id': product['id'], 'source': '售后统计',
                 'baseline_start': '2026-11-01', 'baseline_end': '2026-11-03',
                 'trial_start': '2026-11-04', 'trial_end': '2026-11-06'}
        store.save_after_sales(product['id'], query['source'], query['baseline_start'], query['baseline_end'],
                               {'quality': 2, 'size': 1})
        route = '/api/products/after-sales/compare?'
        self.assertEqual(self.call(route + urlencode(query))[0], 400)
        store.save_after_sales(product['id'], query['source'], query['trial_start'], query['trial_end'],
                               {'quality': 0})
        status, result = self.call(route + urlencode(query))
        self.assertEqual(status, 200)
        self.assertEqual(result['comparison']['differences']['quality'], -2)
        self.assertIsNone(result['comparison']['differences']['size'])
        self.assertEqual(result['comparison']['conclusion'], 'uncertain')
        self.assertEqual(self.call(route + urlencode({**query, 'trial_start': query['baseline_end']}))[0], 400)

    def test_after_sales_summary_keeps_missing_categories_and_corrects_same_window(self):
        store = ProductStore(self.directory.name)
        first = store.save(title='茶杯', content='商品说明', product_index=1)
        second = store.save(title='桌布', content='商品说明', product_index=2)
        route = '/api/products/after-sales'
        report = {'product_id': first['id'], 'source': '售后统计',
                  'period_start': '2026-11-01', 'period_end': '2026-11-03',
                  'counts': {'quality': 0, 'fulfillment': 2}}
        self.assertEqual(self.call(route, report)[0], 200)
        self.assertEqual(self.call(route, {**report, 'counts': {'quality': True}})[0], 400)
        status, saved = self.call(route, {**report, 'counts': {'quality': 0, 'fulfillment': 3}})
        self.assertEqual(status, 200)
        item, = saved['reports']
        self.assertEqual(item['counts'], {'quality': 0, 'fulfillment': 3})
        self.assertEqual(self.call(route + '?product_id=' + second['id']), (200, {'reports': []}))
        csv = 'source,period_start,period_end,quality,fulfillment\n售后统计,2026-11-01,2026-11-03,0,4\n'
        upload = {'product_id': first['id'], 'csv': csv + '无效,2026-11-01,2026-11-03,,-1\n'}
        status, error = self.call(route + '/import', upload)
        self.assertEqual(status, 400)
        self.assertIn('第 3 行', error['error'])
        status, review = self.call(route + '?product_id=' + first['id'])
        self.assertEqual(status, 200)
        self.assertEqual(review, saved)
        followup, = review['reports'][0]['followups']
        self.assertEqual((followup['category'], followup['count']), ('fulfillment', 3))
        status, imported = self.call(route + '/import', {**upload, 'csv': csv})
        self.assertEqual((status, imported['imported']), (200, 1))
        self.assertEqual(imported['reports'][0]['counts'], {'quality': 0, 'fulfillment': 4})
        self.assertEqual(imported['reports'][0]['followups'][0]['count'], 4)
        task = {key: report[key] for key in ('product_id', 'source', 'period_start', 'period_end')}
        task.update(category='fulfillment', owner='运营', goal='核对发货承诺')
        self.assertEqual(self.call(route + '/task', {**task, 'category': 'quality'})[0], 409)
        status, tasks = self.call(route + '/task', task)
        self.assertEqual(status, 200)
        self.assertEqual(tasks['tasks'], [{**task, 'evidence_count': 4, 'revoked': False}])
        store.save_live_preparation(product_ids=[first['id']])
        package_route = '/api/live/preparation/package'
        self.assertEqual(self.call(package_route)[1]['after_sales_tasks'], tasks['tasks'])
        store.save_after_sales(first['id'], task['source'], task['period_start'], task['period_end'], {'fulfillment': 5})
        self.assertEqual(self.call(package_route)[1]['after_sales_tasks'], [])
        self.assertEqual(store.after_sales_tasks([first['id']]), tasks['tasks'])
        self.assertEqual(self.call(route + '/task', task)[0], 200)
        self.assertEqual(self.call(package_route)[1]['after_sales_tasks'][0]['evidence_count'], 5)
        identity = {key: value for key, value in task.items() if key not in {'owner', 'goal'}}
        self.assertEqual(self.call(route + '/task/revoke', identity), (200, {'revoked': True}))
        self.assertEqual(self.call(package_route)[1]['after_sales_tasks'], [])
        self.assertTrue(store.after_sales_tasks([first['id']])[0]['revoked'])
        store.save_live_preparation(product_ids=[second['id']])
        self.assertEqual(self.call(package_route)[1]['after_sales_tasks'], [])

    def test_product_guide_compares_only_verified_current_facts(self):
        store = ProductStore(self.directory.name)
        first = store.save(title='茶杯', content='旧说明', product_index=1, product_facts={
            '材质': {'status': 'verified', 'value': '陶瓷', 'source': '商品标签'},
            '活动': {'status': 'verified', 'value': '半价', 'source': '旧活动',
                     'expires_at': '2020-01-01T00:00:00Z'},
        })
        second = store.save(title='桌布', content='旧说明', product_index=2)
        query = urlencode({'product_id': [second['id'], first['id']], 'fact': ['材质', '活动']}, doseq=True)
        status, result = self.call('/api/products/guide?' + query)
        self.assertEqual(status, 200)
        unknown, verified = result['products']
        self.assertEqual(unknown['product_id'], second['id'])
        self.assertEqual(unknown['facts'], {'材质': None, '活动': None})
        self.assertEqual(verified['facts'], {'材质': {'value': '陶瓷', 'source': '商品标签'}, '活动': None})

    def test_settlement_review_keeps_estimates_and_unknown_costs_distinct(self):
        store = ProductStore(self.directory.name)
        product = store.save(title='茶杯', content='商品说明', product_index=1)
        window = {'source': '商家报表', 'scope': '商品日统计',
                  'period_start': '2026-11-01', 'period_end': '2026-11-01'}
        store.save_business_metrics(product['id'], **window, orders=5, refunds=1)
        payload = {**window, 'product_id': product['id'], 'currency': 'CNY', 'basis': 'estimate',
                   'sales_minor': 10000, 'cost_minor': 3000, 'fees_minor': 0, 'refund_loss_minor': 2000}
        route = '/api/products/settlement-review'
        status, result = self.call(route, payload)
        self.assertEqual(status, 200)
        self.assertEqual(result['review']['net_minor'], 5000)
        self.assertEqual(result['review']['basis'], 'estimate')
        self.assertEqual(result['review']['refunds'], 1)
        self.assertIsNone(result['review']['fulfillment_after_sales'])
        self.assertIsNone(result['review']['on_time_fulfillment_rate'])
        self.assertIsNone(result['review']['inventory_turnover'])
        for opening, closing, sold, expected in [(10, 20, 30, 2), (0, 10, 0, 0), (0, 0, 4, None), (None, 10, 4, None)]:
            status, measured = self.call(route, {**payload, 'inventory_start': opening,
                                                 'inventory_end': closing, 'net_units_sold': sold})
            self.assertEqual(status, 200)
            self.assertEqual(measured['review']['inventory_turnover'], expected)
        self.assertEqual(self.call(route, {**payload, 'net_units_sold': -1})[0], 400)
        for due, on_time, expected in [(4, 3, .75), (4, 0, 0), (0, 0, None), (4, None, None)]:
            status, measured = self.call(route, {**payload, 'fulfillment_due': due, 'fulfilled_on_time': on_time})
            self.assertEqual(status, 200)
            self.assertEqual(measured['review']['on_time_fulfillment_rate'], expected)
        self.assertEqual(self.call(route, {**payload, 'fulfillment_due': 2, 'fulfilled_on_time': 3})[0], 400)
        store.save_after_sales(product['id'], window['source'], window['period_start'],
                               window['period_end'], {'fulfillment': 0})
        status, result = self.call(route, {**payload, 'basis': 'settled', 'fees_minor': None})
        self.assertEqual(status, 200)
        self.assertEqual(result['review']['fulfillment_after_sales'], 0)
        self.assertIsNone(result['review']['net_minor'])
        self.assertEqual(result['review']['missing'], ['fees_minor'])
        self.assertEqual(self.call(route, {**payload, 'fees_minor': True})[0], 400)
        status, result = self.call(route, {**payload, 'sales_minor': 1000})
        self.assertEqual(status, 200)
        self.assertEqual(result['review']['net_minor'], -4000)
        status, error = self.call(route, {**payload, 'period_end': '2026-11-02'})
        self.assertEqual(status, 400)
        self.assertIn('覆盖', error['error'])

    def test_preparation_preserves_manual_lineup_order_through_handoff(self):
        store = ProductStore(self.directory.name)
        first = store.save(title='茶杯', content='口播验收', product_index=1)
        second = store.save(title='桌布', content='口播验收', product_index=2)
        order = [second['id'], first['id']]
        route = '/api/live/preparation'
        self.assertEqual(self.call(route + '/baseline', {})[0], 409)
        self.assertEqual(self.call(route, {'product_ids': order})[0], 200)
        self.assertEqual(self.call(route)[1]['draft']['product_ids'], order)
        status, package = self.call(route + '/package')
        self.assertEqual(status, 200)
        self.assertEqual([item['product_id'] for item in package['items']], order)
        self.assertEqual(self.call(route + '/review', {
            'revision': package['revision'], 'review': '已确认排品顺序',
        })[0], 200)
        status, rotation = self.call(route + '/rotation', {'revision': package['revision']})
        self.assertEqual(status, 200)
        self.assertEqual([item['product_id'] for item in rotation['items']], order)
        status, captured = self.call(route + '/baseline', {})
        self.assertEqual(status, 200)
        self.assertEqual([item['id'] for item in captured['baseline']['lineup']], order)
        self.assertEqual(self.call(route, {'product_ids': list(reversed(order))})[0], 200)
        self.assertEqual(self.call(route + '/baseline'), (200, captured))
        trial = {'session_id': 'trial'}
        self.assertEqual(self.call(route + '/trial', trial)[0], 409)
        store.record_live_session('trial', 1, started_at=2, ended_at=3, status='stopped')
        self.assertEqual(self.call(route + '/trial', trial), (200, {'lineup_baseline': captured['baseline']}))
        self.assertEqual(self.call(route + '/baseline', {})[0], 200)
        self.assertEqual(self.call(route + '/trial', trial)[1]['lineup_baseline'], captured['baseline'])
        self.assertEqual(self.call('/api/live/report?session_id=trial')[1]['lineup_baseline'], captured['baseline'])

    def test_product_selection_requires_verified_primary_role_and_commercial_facts(self):
        store = ProductStore(self.directory.name)
        values = {'适播性': '适播', '目标人群': '家庭', '库存': 20, '发货条件': '48小时内',
                  '排品角色': '主推', '售价': '99元', '成本': '50元'}
        for index, omit in enumerate((None, '成本', '排品角色'), start=1):
            store.save(title=f'商品{index}', content='商品说明', product_index=index, product_facts={
                key: {'status': 'verified', 'source': '商家确认', 'value': value}
                for key, value in values.items() if key != omit
            })
        status, response = self.call('/api/products/selection-evidence')
        self.assertEqual(status, 200)
        self.assertEqual([item['recommendation']['role'] for item in response['products']],
                         ['primary', 'support', 'support'])

    def test_product_selection_evidence_preserves_zero_and_missing_conditions(self):
        store = ProductStore(self.directory.name)
        product = store.save(title='茶杯', content='商品说明', product_index=1, product_facts={
            '库存': {'status': 'verified', 'value': 0, 'source': '盘点'},
            '成本': {'status': 'unknown'},
            '售价': {'status': 'verified', 'value': '人民币 99 元', 'source': '旧活动',
                   'expires_at': '2020-01-01T00:00:00Z'},
        })
        status, response = self.call('/api/products/selection-evidence')
        self.assertEqual(status, 200)
        item, = response['products']
        self.assertEqual(item['product_id'], product['id'])
        self.assertEqual(item['conditions']['库存'], {'value': 0, 'source': '盘点'})
        self.assertIsNone(item['conditions']['成本'])
        self.assertIsNone(item['conditions']['售价'])
        self.assertEqual(item['verified_fact_count'], 1)
        self.assertEqual(item['recommendation'], {'role': 'hold', 'reason': '已核对库存为零'})
        store.save(title='桌布', content='另一商品', product_index=2)
        window = {'source': '商家报表', 'scope': '商品日统计',
                  'period_start': '2026-11-01', 'period_end': '2026-11-01'}
        store.save_business_metrics(product['id'], **window, orders=5, refunds=0)
        route = '/api/products/selection-evidence'
        self.assertEqual(self.call(route + '?source=report')[0], 400)
        status, evidence = self.call(route + '?' + urlencode(window))
        self.assertEqual(status, 200)
        self.assertEqual(evidence['business_metrics_scope'], window)
        first, second = evidence['products']
        self.assertEqual(first['business_metrics']['orders'], 5)
        self.assertEqual(first['business_metrics']['refunds'], 0)
        self.assertIsNone(second['business_metrics'])
        self.assertEqual(second['recommendation']['role'], 'hold')
        self.assertIn('覆盖', second['business_metrics_gap'])
        self.assertNotIn('refund_review', first)
        store.save_business_metrics(product['id'], **window, orders=5, refunds=6)
        updated = self.call(route + '?' + urlencode(window))[1]['products'][0]
        self.assertEqual(updated['business_metrics']['refunds'], 6)
        self.assertIn('退款多于订单', updated['refund_review'])

    def test_live_content_source_preserves_original_product_and_script(self):
        store = ProductStore(self.directory.name)
        product = store.save(title='茶杯', content='原商品资料', product_index=1)
        script_id = store.add_script(product, '原口播')
        store.record_rotation_completion('scene', 'task', {
            'product_id': product['id'], 'product_version': product['version'], 'script_id': script_id,
        }, 0, sample_start=960, sample_end=1920, voice_id='host-voice',
           speech_provenance={'engine': 'indextts', 'language': 'zh-CN'})
        store.save(title='新版茶杯', content='更新资料', product_index=1,
                   product_id=product['id'], version=product['version'])
        status, result = self.call('/api/live/content-source?session_id=scene&task_id=task')
        self.assertEqual(status, 200)
        source = result['source']
        self.assertEqual(source['product_snapshot'], product)
        self.assertEqual(source['facts_review'], 'product_changed')
        self.assertEqual(source['voice_id'], 'host-voice')
        self.assertEqual(source['speech_provenance'], {'engine': 'indextts', 'language': 'zh-CN'})
        self.assertEqual(source['script_text'], '原口播')
        self.assertEqual(source['segment'], {'type': 'host', 'content': '原口播'})
        segmented_id = store.add_script(store.get(product['id']), '主讲。{助：补充说明。}')
        store.record_rotation_completion('scene', 'assistant-task', {
            'product_id': product['id'], 'product_version': product['version'] + 1, 'script_id': segmented_id,
        }, 1, sample_start=24000, sample_end=60000)
        assistant = self.call('/api/live/content-source?session_id=scene&task_id=assistant-task')[1]['source']
        self.assertEqual(assistant['segment'], {'type': 'assistant', 'content': '补充说明。'})
        self.assertEqual(assistant['facts_review'], 'version_current')
        draft_route = '/api/live/content-draft?session_id=scene&task_id='
        self.assertEqual(self.call(draft_route + 'task')[0], 409)
        status, result = self.call(draft_route + 'assistant-task')
        self.assertEqual(status, 200)
        self.assertEqual(result['draft']['cover_text'], '新版茶杯')
        self.assertEqual(result['draft']['narration'], '补充说明。')
        self.assertEqual(result['draft']['subtitle_srt'], '1\n00:00:00,000 --> 00:00:01,500\n补充说明。\n')
        self.assertEqual(result['draft']['source']['script_id'], segmented_id)
        self.assertIsNone(result['draft']['language'])
        self.assertIsNone(result['draft']['saved_body'])
        body = {'session_id': 'scene', 'task_id': 'assistant-task', 'body': '运营修改后的文案'}
        schedule_route = '/api/live/content-schedule'
        schedule = {'session_id': 'scene', 'task_id': 'assistant-task', 'account': '店铺账号',
                    'audience': '公开', 'publish_at': '2027-01-01T09:00:00+08:00'}
        self.assertEqual(self.call(schedule_route, schedule)[0], 409)
        self.assertEqual(self.call('/api/live/content-withdraw', {
            'session_id': 'scene', 'task_id': 'task',
        })[0], 409)
        self.assertEqual(self.call('/api/live/content-draft', body), (200, {'body': body['body']}))
        self.assertEqual(self.call(schedule_route, {**schedule, 'publish_at': '2027-01-01T09:00'})[0], 400)
        status, saved_schedule = self.call(schedule_route, schedule)
        self.assertEqual(status, 200)
        self.assertEqual(saved_schedule['schedule']['publish_at'], '2027-01-01T01:00:00+00:00')
        self.assertTrue(saved_schedule['schedule']['draft_matches'])
        self.assertEqual(self.call('/api/live/content-draft', {**body, 'body': '改稿'})[0], 200)
        self.assertFalse(self.call(schedule_route + '?session_id=scene&task_id=assistant-task')[1]['schedule']['draft_matches'])
        receipt_route = '/api/live/content-receipt'
        receipt = {'session_id': 'scene', 'task_id': 'assistant-task', 'publication_id': 'platform-001'}
        self.assertEqual(self.call(receipt_route, receipt)[0], 409)
        self.assertEqual(self.call('/api/live/content-draft', body)[0], 200)
        self.assertEqual(self.call(receipt_route, {**receipt, 'task_id': 'task'})[0], 409)
        self.assertEqual(self.call(receipt_route, receipt)[1]['schedule']['publication_id'], 'platform-001')
        self.assertEqual(self.call(receipt_route, receipt)[0], 200)
        self.assertEqual(self.call(receipt_route, {**receipt, 'publication_id': 'platform-002'})[0], 409)
        self.assertEqual(self.call(schedule_route, schedule)[0], 409)
        self.assertEqual(self.call(draft_route + 'assistant-task')[1]['draft']['saved_body'], body['body'])
        self.assertEqual(self.call('/api/live/content-draft', {**body, 'task_id': 'task'})[0], 409)
        current = store.get(product['id'])
        store.save(title='再次更新', content='新资料', product_index=1,
                   product_id=product['id'], version=current['version'])
        self.assertEqual(self.call(draft_route + 'assistant-task'),
                         (200, {'draft': {'saved_body': body['body'], 'editable': False}}))
        self.assertEqual(self.call('/api/live/content-draft', body)[0], 409)
        self.assertEqual(self.call(schedule_route, schedule)[0], 409)
        self.assertEqual(self.call('/api/live/content-withdraw', {
            'session_id': 'scene', 'task_id': 'assistant-task',
        }), (200, {'withdrawn': True}))
        self.assertTrue(self.call(draft_route + 'assistant-task')[1]['draft']['withdrawn'])
        self.assertTrue(self.call(schedule_route + '?session_id=scene&task_id=assistant-task')[1]['schedule']['withdrawn'])
        self.assertEqual((source['sample_start'], source['sample_end']), (960, 1920))
        self.assertEqual(self.call('/api/live/content-source?session_id=other&task_id=task')[0], 400)

    def test_live_advice_only_reports_current_explicit_faults(self):
        route = '/api/live/advice'
        self.assertEqual(self.call(route), (200, {'session_id': None, 'advice': []}))
        with (patch('scripts.local_console.ConsoleLive') as live,
              patch('scripts.local_console.preflight', return_value={'runtime_root': self.directory.name}),
              patch('scripts.tts_tasks.TTSTasks')):
            live.return_value.start.return_value = {'id': 'scene'}
            self.assertEqual(self.call('/api/live/start', {'audio_device': 1})[0], 202)
            live.return_value.state.return_value = {'id': 'scene', 'status': 'running', 'rotation_error': '合成超时'}
            status, payload = self.call(route)
            self.assertEqual((status, payload['session_id']), (200, 'scene'))
            advice, = payload['advice']
            self.assertEqual(self.call('/api/live/state')[1]['advice'], payload['advice'])
            self.assertEqual((advice['code'], advice['evidence']), ('rotation_error', '合成超时'))
            store = ProductStore(self.directory.name)
            store.record_live_session('scene', 1)
            acknowledge = {'session_id': 'scene', 'advice': advice}
            self.assertEqual(self.call(route + '/acknowledge', {**acknowledge, 'session_id': 'old'})[0], 409)
            self.assertEqual(self.call(route + '/acknowledge', acknowledge)[0], 200)
            self.assertEqual(self.call(route + '/acknowledge', acknowledge)[0], 200)
            entry, = self.call('/api/live/report?session_id=scene')[1]['advice_acknowledgments']
            self.assertEqual(entry['advice'], advice)
            self.assertIsNone(entry['revoked_at'])
            self.assertEqual(self.call('/api/live/state')[1]['acknowledged'], [advice])
            self.assertEqual(self.call(route + '/revoke', acknowledge), (200, {'acknowledged': False}))
            revoked, = self.call('/api/live/report?session_id=scene')[1]['advice_acknowledgments']
            self.assertEqual(revoked['acknowledged_at'], entry['acknowledged_at'])
            self.assertIsNotNone(revoked['revoked_at'])
            self.assertEqual(self.call('/api/live/state')[1]['acknowledged'], [])
            self.assertEqual(self.call(route + '/acknowledge', acknowledge)[0], 200)
            renewed, = self.call('/api/live/report?session_id=scene')[1]['advice_acknowledgments']
            self.assertIsNone(renewed['revoked_at'])
            actions = self.call('/api/live/report?session_id=scene')[1]['advice_actions']
            self.assertEqual([item['action'] for item in actions], ['acknowledge', 'revoke', 'acknowledge'])
            live.return_value.state.return_value['rotation_error'] = None
            self.assertEqual(self.call(route + '/acknowledge', acknowledge)[0], 409)
            self.assertEqual(self.call(route)[1]['advice'], [])
            live.return_value.state.return_value.update(automatic_queue_full=True, pending=4)
            advice, = self.call(route)[1]['advice']
            self.assertEqual(advice['code'], 'automatic_queue_full')
            self.assertIn('待播 4 条', advice['evidence'])
            live.return_value.state.return_value.update(automatic_queue_full=False, pending=3)
            self.assertEqual(self.call(route)[1]['advice'], [])
            live.return_value.state.return_value.update(status='failed', ended_at=100,
                                                       device_underrun={'next_frame': 25})
            advice, = self.call(route)[1]['advice']
            self.assertEqual(advice['code'], 'device_underrun')
            self.assertEqual(advice['context'], {'occurred_at': 100, 'next_frame': 25})
            live.return_value.state.return_value.pop('device_underrun')
            self.assertEqual(self.call(route)[1]['advice'], [])
            live.return_value.state.return_value['status'] = 'running'
            product = {'id': 'product', 'version': 1}
            store.record_queued_reply('scene', 'a', product, '库存？', '待核对', 100)
            store.record_queued_reply('scene', 'b', product, '库存？ ', '待核对', 101)
            store.record_queued_reply('other', 'c', product, '库存？', '待核对', 102)
            with patch('time.time', return_value=399):
                advice, = self.call(route)[1]['advice']
                self.assertEqual(advice['code'], 'repeated_question')
                self.assertIn('2 次', advice['evidence'])
                self.assertEqual(advice['context']['task_id'], 'b')
            with patch('time.time', return_value=401):
                self.assertEqual(self.call(route)[1]['advice'], [])

    def test_live_comparison_requires_distinct_ended_sessions(self):
        store = ProductStore(self.directory.name)
        store.record_live_session('baseline', 1, started_at=2, ended_at=3, status='stopped')
        store.record_live_session('trial', 4, started_at=5, status='running')
        route = '/api/live/compare?baseline=baseline&trial='
        self.assertEqual(self.call(route + 'baseline')[0], 400)
        self.assertEqual(self.call(route + 'trial')[0], 400)
        store.record_live_session('trial', 4, started_at=5, ended_at=6, status='stopped')
        store.record_rotation_completion('trial', 'segment', {
            'product_id': 'product', 'product_version': 1, 'script_id': 'script',
        }, 0)
        status, comparison = self.call(route + 'trial')
        self.assertEqual(status, 200)
        self.assertEqual(comparison['baseline']['completed_segments'], 0)
        self.assertEqual(comparison['trial']['completed_segments'], 1)
        self.assertEqual(comparison['baseline']['products'], [])
        product, = comparison['trial']['products']
        self.assertEqual((product['product_id'], product['product_version'], product['script_id']),
                         ('product', 1, 'script'))
        self.assertEqual(comparison['trial']['duration_seconds'], 1)
        self.assertEqual(comparison['trial']['completed_segments_per_minute'], 60)
        store.record_live_session('failed-start', 7, ended_at=8, status='failed')
        status, comparison_with_failed_start = self.call(route + 'failed-start')
        self.assertEqual(status, 200)
        self.assertIsNone(comparison_with_failed_start['trial']['duration_seconds'])
        self.assertIsNone(comparison_with_failed_start['trial']['completed_segments_per_minute'])
        self.assertEqual(comparison['conclusion'], 'uncertain')
        self.assertIn('refund_lag', comparison['missing'])

    def test_live_report_isolates_sessions_and_keeps_missing_metrics_explicit(self):
        store = ProductStore(self.directory.name)
        store.record_live_session('scene', 100, started_at=101, ended_at=110, status='failed', frames=225,
                                  failure_reason='输出设备断开')
        store.record_live_session('other', 200)
        product = store.save(title='茶杯', content='验收商品', product_index=1)
        item = {'product_id': product['id'], 'product_version': 2, 'script_id': 'script'}
        store.record_rotation_completion('scene', 'first', item, 0)
        store.record_rotation_completion('scene', 'first', item, 0)
        store.record_rotation_completion('scene', 'second', item, 1)
        store.record_rotation_completion('other', 'first', item, 0)
        store.record_rotation_completion('scene', 'third', {**item, 'product_id': 'next-product'}, 0)
        store.record_live_control('scene', 1, True, 103)
        store.record_rotation_fault('scene', 104, '语音合成超时', item=item)
        store.record_rotation_fault('other', 105, '其他场次故障')
        store.record_queued_reply('scene', 'reply', {'id': 'product', 'version': 2}, '什么材质？', '陶瓷', 106)
        store.record_queued_reply('other', 'reply', {'id': 'product', 'version': 2}, '其他问题', '其他回答', 107)
        store.record_reply_playback('scene', 'reply', 108)
        store.record_reply_playback('scene', 'reply', 109)
        store.record_unqueued_reply('scene', {'id': 'product', 'version': 2}, '何时发货？',
                                   'cancelled', '场次变化', 110)
        status, report = self.call('/api/live/report?session_id=scene')
        self.assertEqual(status, 200)
        self.assertEqual(report['session']['frames'], 225)
        self.assertEqual(report['queued_replies'], [{
            'task_id': 'reply', 'product_id': 'product', 'product_version': 2,
            'question': '什么材质？', 'answer': '陶瓷', 'queued_at': 106, 'played_at': 108,
            'verdict': None, 'review_seconds': None,
        }])
        review_payload = {'session_id': 'scene', 'task_id': 'reply', 'verdict': 'correct', 'review_seconds': 0}
        self.assertEqual(self.call('/api/live/reply-review', {**review_payload, 'task_id': 'missing'})[0], 400)
        self.assertEqual(self.call('/api/live/reply-review', review_payload), (200, {'saved': True}))
        reviewed = self.call('/api/live/report?session_id=scene')[1]['queued_replies'][0]
        self.assertEqual((reviewed['verdict'], reviewed['review_seconds']), ('correct', 0))
        self.assertEqual(report['session']['failure_reason'], '输出设备断开')
        self.assertEqual(report['rotation_faults'], [
            {'event_id': 1, 'occurred_at': 104, 'reason': '语音合成超时', **item},
        ])
        store.record_queued_reply('scene', 'second-reply', {'id': 'product', 'version': 3}, ' 什么材质？ ', '陶瓷', 109)
        status, review = self.call('/api/live/review?session_id=scene')
        self.assertEqual(status, 200)
        finding, = review['findings']
        self.assertEqual(finding['evidence'], {'event_id': 1, 'occurred_at': 104})
        self.assertEqual(finding['fact'], '语音合成超时')
        task_route = '/api/live/improvements'
        task = {'session_id': 'scene', 'fault_id': 1, 'owner': '运营', 'goal': '复测语音合成'}
        self.assertEqual(self.call(task_route, {**task, 'session_id': 'other'})[0], 400)
        self.assertEqual(self.call(task_route, task)[0], 200)
        status, saved = self.call(task_route, {**task, 'goal': '复测两次语音合成'})
        self.assertEqual(status, 200)
        self.assertEqual(saved['tasks'], [{
            'session_id': 'scene', 'fault_id': 1, 'owner': '运营', 'goal': '复测两次语音合成', 'adopted': False,
            'reason': '语音合成超时', 'occurred_at': 104, **item,
        }])
        self.assertEqual(self.call(task_route + '?session_id=scene'), (200, saved))
        store.save_live_preparation(product_ids=[product['id']])
        package_route = '/api/live/preparation/package'
        self.assertEqual(self.call(package_route)[1]['improvements'], [])
        self.assertEqual(self.call(task_route, {**task, 'adopted': True})[0], 200)
        self.assertEqual(self.call(package_route)[1]['improvements'][0]['fault_id'], 1)
        unrelated = store.save(title='桌布', content='另一场商品', product_index=2)
        store.save_live_preparation(product_ids=[unrelated['id']])
        self.assertEqual(self.call(package_route)[1]['improvements'], [])
        store.save_live_preparation(product_ids=[product['id']])
        self.assertEqual(self.call(task_route, {**task, 'adopted': False})[0], 200)
        self.assertEqual(self.call(package_route)[1]['improvements'], [])
        self.assertIn('questions_and_answers', review['missing'])
        unqueued, = review['unqueued_replies']
        self.assertEqual((unqueued['question'], unqueued['status'], unqueued['reason']),
                         ('何时发货？', 'cancelled', '场次变化'))
        question, = review['repeated_questions']
        self.assertEqual(question['question'], '什么材质？')
        self.assertIn('FAQ', question['recommendation'])
        self.assertEqual([item['task_id'] for item in question['evidence']], ['reply', 'second-reply'])
        self.assertIsNone(question['evidence'][1]['played_at'])
        pending, = review['replies_without_playback_record']
        self.assertEqual(pending['task_id'], 'second-reply')
        self.assertEqual(pending['product_version'], 3)
        first_product, next_product = report['products']
        self.assertEqual(first_product['completed_segments'], 2)
        self.assertEqual(next_product['completed_segments'], 1)
        switch, = report['observed_product_switches']
        self.assertEqual((switch['previous_product_id'], switch['product_id'], switch['task_id']),
                         (product['id'], 'next-product', 'third'))
        self.assertIn('platform_product_switches', report['missing'])
        self.assertEqual(first_product['product_version'], 2)
        self.assertEqual(report['controls'], [{'revision': 1, 'manual': True, 'occurred_at': 103}])
        self.assertIn('attributed_sales', report['missing'])
        self.assertEqual(self.call('/api/live/report?session_id=unknown')[0], 400)

    def test_prepared_rotation_rejects_changed_script_before_configuring_live(self):
        store = ProductStore(self.directory.name)
        product = store.save(title='茶杯', content='口播验收', product_index=1)
        product_id = product['id']
        first = store.add_script(product, '第一版话术')
        replacement = store.add_script(product, '第二版话术')
        store.select_script(product_id, first)
        store.save_live_preparation(product_ids=[product_id])
        revision = store.build_live_preparation()['revision']
        store.save_live_preparation_review(revision, '已核对')
        items = [{'product_id': product_id, 'product_version': product['version'], 'script_id': first}]
        request = {'session_id': 'scene', 'product_ids': [product_id],
                   'preparation': {'revision': revision, 'items': items}}
        with (patch('scripts.local_console.ConsoleLive') as live,
              patch('scripts.local_console.preflight', return_value={'runtime_root': self.directory.name}),
              patch('scripts.tts_tasks.TTSTasks')):
            live.return_value.start.return_value = {'id': 'scene'}
            live.return_value.configure_rotation.return_value = {'id': 'scene'}
            self.assertEqual(self.call('/api/live/start', {'audio_device': 1})[0], 202)
            store.select_script(product_id, replacement)
            self.assertEqual(self.call('/api/live/rotation', request)[0], 409)
            live.return_value.configure_rotation.assert_not_called()
            store.select_script(product_id, first)
            self.assertEqual(self.call('/api/live/rotation', request)[0], 200)
            live.return_value.configure_rotation.assert_called_once_with(
                'scene', [product_id], shift_durations=None, shift_voice_ids=None, expected_items=items)

    def test_live_preparation_package_uses_only_current_sourced_facts(self):
        route = '/api/live/preparation'
        self.assertEqual(self.call(route + '/package')[0], 400)
        _, response = self.call('/api/products', {
            'title': '茶杯', 'content': '旧说明中的活动', 'product_index': 1,
            'product_facts': {
                '材质': {'value': '陶瓷', 'status': 'verified', 'source': '商品标签'},
                '优惠': {'value': '半价', 'status': 'verified', 'source': '旧报表',
                       'expires_at': '2020-01-01T00:00:00Z'},
                '库存': {'status': 'unknown'},
            },
        })
        product = response['product']
        self.assertEqual(self.call(route, {'product_ids': [product['id']]})[0], 200)
        status, package = self.call(route + '/package')
        self.assertEqual(status, 200)
        item, = package['items']
        self.assertEqual(item['product_version'], product['version'])
        self.assertEqual(item['selling_points'], [{'name': '材质', 'value': '陶瓷', 'source': '商品标签'}])
        self.assertEqual(item['faq'], [{'question': '材质是什么？', 'answer': '陶瓷', 'source': '商品标签'}])
        self.assertIn('发货条件', package['missing'])
        self.assertEqual(set(package['segments']), {'opening', 'transition', 'closing'})
        review = {'revision': package['revision'], 'review': '商家确认：陶瓷杯。'}
        self.assertEqual(self.call(route + '/rotation', {'revision': package['revision']})[0], 409)
        self.assertEqual(self.call(route + '/review', review)[0], 200)
        self.assertEqual(self.call(route + '/package')[1]['review'], review['review'])
        status, rotation = self.call(route + '/rotation', {'revision': package['revision']})
        self.assertEqual(status, 200)
        self.assertEqual(rotation['items'][0]['product_id'], product['id'])
        self.assertIsNone(rotation['items'][0]['script_id'])
        store = ProductStore(self.directory.name)
        script_id = store.add_script(product, '这是一只陶瓷杯。')
        store.select_script(product['id'], script_id)
        self.assertEqual(self.call(route + '/rotation', {'revision': package['revision']})[1]['items'][0]['script_id'],
                         script_id)
        self.assertEqual(self.call(route, {'product_ids': [product['id']], 'goal': '新品介绍'})[0], 200)
        self.assertIsNone(self.call(route + '/package')[1]['review'])
        self.assertEqual(self.call(route + '/review', review)[0], 409)

    def test_live_preparation_draft_and_missing_conditions(self):
        route = '/api/live/preparation'
        self.assertIn('本场商品', self.call(route)[1]['missing'])
        _, response = self.call('/api/products', {'title': '茶杯', 'content': '测试', 'product_index': 1})
        product_id = response['product']['id']
        draft = {'product_ids': [product_id], 'goal': ' 介绍新品 '}
        status, saved = self.call(route, draft)
        self.assertEqual(status, 200)
        self.assertEqual(saved['draft']['goal'], '介绍新品')
        self.assertNotIn('本场商品', saved['missing'])
        self.assertIn('发货条件', saved['missing'])
        self.assertEqual(self.call(route, {**draft, 'product_ids': [product_id, product_id]})[0], 400)
        self.assertEqual(self.call(route), (200, saved))

    def test_business_metrics_api_preserves_zero_and_unknown(self):
        _, response = self.call('/api/products', {'title': '茶杯', 'content': '经营数据', 'product_index': 1})
        product = response['product']
        route = '/api/products/business-metrics'
        payload = {'product_id': product['id'], 'source': '商家报表', 'scope': '商品日统计',
                   'period_start': '2026-11-01', 'period_end': '2026-11-01', 'clicks': 0}
        self.assertEqual(self.call(route, payload, **{'X-Console-Token': 'bad'})[0], 403)
        self.assertEqual(self.call(route, {**payload, 'orders': True})[0], 400)
        status, result = self.call(route, payload)
        self.assertEqual(status, 200)
        self.assertEqual(result['records'][0]['clicks'], 0)
        self.assertIsNone(result['records'][0]['orders'])
        self.assertEqual(self.call(route + '?product_id=' + product['id']), (200, result))
        header = 'source,period_start,period_end,scope,clicks,stock\n'
        report = header + '人工盘点,2026-11-02,2026-11-02,商品,,0\n'
        upload = {'product_id': product['id'], 'csv': report}
        self.assertEqual(self.call(route + '/import', upload, **{'X-Console-Token': 'bad'})[0], 403)
        status, imported = self.call(route + '/import', upload)
        self.assertEqual((status, imported['imported']), (200, 1))
        self.assertEqual(imported['records'][0]['stock'], 0)
        self.assertIsNone(imported['records'][0]['clicks'])
        self.assertEqual(self.call(route + '/import', {**upload, 'csv': report + 'bad\n'})[0], 400)
        invalid = '人工盘点,2026-11-03,2026-11-03,商品,,-1\n'
        status, error = self.call(route + '/import', {**upload, 'csv': report + invalid})
        self.assertEqual(status, 400)
        self.assertIn('第 3 行', error['error'])
        self.assertIn('库存', error['error'])
        self.assertEqual(len(self.call(route + '?product_id=' + product['id'])[1]['records']), 2)
        large_report = header + '人工盘点,2026-11-03,2026-11-03,商品,9007199254740993,0\n'
        status, imported = self.call(route + '/import', {**upload, 'csv': large_report})
        self.assertEqual(status, 200)
        self.assertEqual(imported['records'][0]['clicks'], '9007199254740993')
        self.assertEqual(imported['records'][0]['stock'], 0)
        status, listed = self.call(route + '?product_id=' + product['id'])
        self.assertEqual((status, listed['records']), (200, imported['records']))

    def test_business_metrics_summary_uses_corrected_complete_coverage(self):
        _, response = self.call('/api/products', {'title': '茶杯', 'content': '经营数据', 'product_index': 1})
        route = '/api/products/business-metrics'
        base = {'product_id': response['product']['id'], 'source': '商家报表', 'scope': '商品日统计'}
        for day, orders, stock in [('2026-11-01', 5, 9), ('2026-11-02', 3, 7)]:
            status, _ = self.call(route, {**base, 'period_start': day, 'period_end': day,
                                          'orders': orders, 'stock': stock, 'refunds': 0})
            self.assertEqual(status, 200)
        period = {'period_start': '2026-11-01', 'period_end': '2026-11-02'}
        summary_url = route + '/summary?' + urlencode({**base, **period})
        expected = {'clicks': None, 'orders': 8, 'refunds': 0, 'closing_stock': 7}
        self.assertEqual(self.call(summary_url), (200, {'summary': expected}))
        correction = {**base, 'period_start': '2026-11-01', 'period_end': '2026-11-01',
                      'orders': 6, 'refunds': 2, 'stock': 9}
        self.assertEqual(self.call(route, correction)[0], 200)
        self.assertEqual(self.call(summary_url), (200, {'summary': {**expected, 'orders': 9, 'refunds': 2}}))
        self.assertEqual(self.call(route, {**base, **period, 'orders': 9})[0], 200)
        self.assertEqual(self.call(summary_url)[0], 400)

    def test_business_metrics_summary_rejects_incomplete_or_partial_reports(self):
        route = '/api/products/business-metrics'
        _, response = self.call('/api/products', {'title': '茶杯', 'content': '经营数据', 'product_index': 1})
        base = {'product_id': response['product']['id'], 'source': '商家报表', 'scope': '商品日统计'}
        first_report = {'period_start': '2026-11-01', 'period_end': '2026-11-02'}
        last_report = {'period_start': '2026-11-04', 'period_end': '2026-11-04'}
        for period in (first_report, last_report):
            self.assertEqual(self.call(route, {**base, **period, 'orders': 1})[0], 200)
        for start, end in [('01', '04'), ('02', '02'), ('01', '01'), ('01', '03'), ('05', '05')]:
            with self.subTest(start=start, end=end):
                query = urlencode({**base, 'period_start': '2026-11-' + start,
                                   'period_end': '2026-11-' + end})
                status, error = self.call(route + '/summary?' + query)
                self.assertEqual(status, 400)
                self.assertIn('覆盖', error['error'])
        self.assertEqual(self.call(route + '/summary?' + urlencode({**base, **first_report}))[0], 200)

    def test_business_metrics_summary_preserves_large_integer_totals(self):
        route = '/api/products/business-metrics'
        _, response = self.call('/api/products', {'title': '茶杯', 'content': '经营数据', 'product_index': 1})
        base = {'product_id': response['product']['id'], 'source': '商家报表', 'scope': '商品日统计'}
        for day, orders in [('2026-11-01', 2**53 - 1), ('2026-11-02', 2)]:
            self.assertEqual(self.call(route, {**base, 'period_start': day, 'period_end': day,
                                               'orders': orders, 'refunds': 0})[0], 200)
        query = urlencode({**base, 'period_start': '2026-11-01', 'period_end': '2026-11-02'})
        self.assertEqual(self.call(route + '/summary?' + query), (200, {'summary': {
            'clicks': None, 'orders': str(2**53 + 1), 'refunds': 0, 'closing_stock': None,
        }}))

    def test_rotation_event_pages_preserve_order_and_scene_isolation(self):
        store = ProductStore(self.directory.name)
        product = store.save(title='茶杯', content='口播验收', product_index=1)
        script = store.add_script(product, '这是一只茶杯。')
        item = {'product_id': product['id'], 'product_version': product['version'], 'script_id': script}
        store.record_live_session('scene', 100, started_at=101, ended_at=110, status='stopped', frames=225)
        store.record_live_session('another-scene', 120)
        store.record_live_control('scene', 1, True, 103)
        store.record_live_control('scene', 2, False, 104)
        store.record_live_control('another-scene', 1, True, 121)
        status, controls = self.call('/api/live/control/events?session_id=scene')
        self.assertEqual(status, 200)
        self.assertEqual(controls['events'], [
            {'revision': 1, 'manual': True, 'occurred_at': 103},
            {'revision': 2, 'manual': False, 'occurred_at': 104},
        ])
        status, history = self.call('/api/live/history')
        self.assertEqual(status, 200)
        self.assertEqual([row['session_id'] for row in history['sessions']], ['another-scene', 'scene'])
        for index in range(101):
            store.record_rotation_completion('scene', str(index), item, 0)
            store.record_rotation_completion('another-scene', str(index), item, 0)

        route = '/api/live/rotation/events?session_id=scene'
        status, first = self.call(route)
        self.assertEqual(status, 200)
        self.assertEqual(first['session']['frames'], 225)
        self.assertEqual(first['session']['status'], 'stopped')
        self.assertEqual([row['task_id'] for row in first['events']], [str(index) for index in range(100)])
        status, second = self.call(route + '&after=' + str(first['next_cursor']))
        self.assertEqual(status, 200)
        self.assertEqual([row['task_id'] for row in second['events']], ['100'])
        self.assertTrue(all(row['session_id'] == 'scene' for row in first['events'] + second['events']))
        self.assertEqual(self.call(route + '&after=' + str(second['next_cursor']))[1]['events'], [])
        filtered = self.call(route + '&product_id=' + product['id'] + '&task_id=100')[1]['events']
        self.assertEqual([row['task_id'] for row in filtered], ['100'])
        self.assertEqual(self.call(route + '&product_id=other&task_id=100')[1]['events'], [])
        self.assertEqual(self.call(route + '&task_id=100&task_id=99')[0], 400)

    def test_taobao_routes_require_login_explicit_room_and_console_token(self):
        state = self.call('/api/taobao/state')[1]['capture']
        self.assertEqual(state['status'], 'idle')
        self.assertFalse(state['saved_login'])
        self.assertEqual(self.call('/api/taobao/start', {'live_id':'https://example.com'})[0], 400)
        self.assertEqual(self.call('/api/taobao/start', {'live_id':'123456'})[0], 409)
        self.assertEqual(self.call('/api/taobao/login', {}, **{'X-Console-Token':'invalid'})[0], 403)
        self.assertEqual(self.call('/api/taobao/stop', {})[0], 200)
        self.assertEqual(self.call('/api/taobao/reply', {'comment_id':1})[0], 400)
        self.assertEqual(self.call('/api/taobao/reply', {'capture_id':'old', 'comment_id':1})[0], 409)
        self.assertEqual(self.call('/api/taobao/auto-reply', {'enabled':'true'})[0], 400)
        self.assertEqual(self.call('/api/taobao/auto-reply', {'enabled':True})[0], 409)
        self.assertFalse(self.call('/api/taobao/auto-reply', {'enabled':False})[1]['reply']['automatic'])
        self.assertEqual(self.call('/api/taobao/goods', {'capture_id':'old'})[0], 409)
        self.assertEqual(self.call('/api/taobao/explain', {'capture_id':'old','goods_id':'123456'})[0], 409)
        self.assertEqual(self.call('/api/taobao/explain', {'capture_id':'old','goods_id':123456})[0], 400)

    def test_live_routes_reject_stale_or_unauthorized_actions(self):
        self.assertEqual(self.call('/api/live/state')[1], {'session': {'status': 'idle'}, 'advice': [], 'acknowledged': []})
        self.assertEqual(self.call('/api/live/rotation/events?session_id=scene&after=7')[1],
                         {'session': None, 'events': [], 'next_cursor': 7})
        self.assertEqual(self.call('/api/live/rotation/events?session_id=scene&after=-1')[0], 400)
        self.assertEqual(self.call('/api/live/start', {'audio_device': True})[0], 400)
        self.assertEqual(self.call('/api/live/start', {'audio_device': 14})[0], 400)
        self.assertEqual(self.call('/api/live/start', {'audio_device': 14}, **{'X-Console-Token': 'bad'})[0], 403)
        self.assertEqual(self.call('/api/live/enqueue', {'session_id': 'old', 'task_id': 'old'})[0], 409)
        self.assertEqual(self.call('/api/live/insert', {'session_id': 'old', 'task_id': 'old'})[0], 409)
        self.assertEqual(self.call('/api/live/rotation', {'session_id': 'old', 'product_ids': ['a', 'a']})[0], 400)
        self.assertEqual(self.call('/api/live/rotation', {'session_id': 'old', 'product_ids': []})[0], 409)
        self.assertEqual(self.call('/api/live/stop', {'session_id': 'old'})[0], 409)

    def test_render_endpoints_require_inputs_and_valid_session(self):
        self.assertEqual(self.call('/api/render/state')[1],{'task':None})
        self.assertEqual(self.call('/api/render/start',{})[0],400)
        request={'tts_task_id':'absent','avatar_id':'absent'}
        self.assertEqual(self.call('/api/render/start',request)[0],400)
        self.assertEqual(self.call('/api/render/start',request,**{'X-Console-Token':'bad'})[0],403)
        self.assertEqual(self.call('/api/render/cancel',{'task_id':0})[0],400)
        self.assertEqual(self.call('/api/render/video')[0],400)

    def test_video_backend_is_validated_before_loading_the_runtime(self):
        cases = [
            ({'audio_device': 14, 'video_backend': 'tensorrt'}, '请选择本地驱动视频'),
            ({'audio_device': 14, 'video_path': 'unused.mp4', 'video_backend': 'other'}, '本地视频推理后端无效'),
            ({'audio_device': 14, 'video_path': 'unused.mp4', 'assistant_voice_id': 'voice'}, '本地视频模式的开播字段无效'),
        ]
        for payload, message in cases:
            with self.subTest(payload=payload):
                status, result = self.call('/api/live/start', payload)
                self.assertEqual(status, 400)
                self.assertEqual(result['error'], message)
        self.assertEqual(self.call('/api/live/state')[1]['session']['status'], 'idle')

    def test_avatar_preparation_requires_config_and_valid_fields(self):
        self.assertEqual(self.call('/api/avatar-preparation/state')[1],{'task':None})
        self.assertEqual(self.call('/api/avatar-preparation/start',{})[0],400)
        request={'source':str(Path(self.directory.name)/'absent.mp4'),'name':'形象','resolution':'720p'}
        self.assertEqual(self.call('/api/avatar-preparation/start',request)[0],400)
        self.assertEqual(self.call('/api/avatar-preparation/cancel',{'task_id':0})[0],400)
        self.assertEqual(self.call('/api/avatar-preparation/start',request,**{'X-Console-Token':'bad'})[0],403)

    def test_owned_avatar_import_selection_and_preview(self):
        import cv2
        import numpy as np
        root=Path(self.directory.name)/'source-avatar'
        (root/'frames').mkdir(parents=True);(root/'positions').mkdir()
        cv2.imwrite(str(root/'frames/000000.jpg'),np.full((32,24,3),100,np.uint8))
        (root/'positions/000000.txt').write_text('fps: 25\nwidth: 24\nheight: 32\nis_no_face: False\nbounding_box: [2, 20, 3, 22]\n')
        status,value=self.call('/api/avatars/import',{'source':str(root),'name':'HTTP媒体测试形象'})
        self.assertEqual(status,201,value)
        avatar_id=value['avatar']['id']
        self.assertEqual(self.call('/api/avatars/select',{'avatar_id':avatar_id})[0],200)
        self.assertEqual(self.call('/api/avatars')[1]['selected'],avatar_id)
        with urlopen(self.base+'/api/avatars/sample?id='+avatar_id,timeout=3) as response:
            self.assertEqual(response.headers['Content-Type'],'image/jpeg')
            self.assertEqual(response.read(2),b'\xff\xd8')
        self.assertEqual(self.call('/api/avatars/sample?id=../console.json')[0],400)
        self.assertEqual(self.call('/api/avatars/import',{'source':str(root),'name':'坏请求','extra':1})[0],400)
        self.assertEqual(self.call('/api/avatars/select',{'avatar_id':'invalid'})[0],400)
        (Path(self.directory.name)/'avatars'/avatar_id/'frames/000000.jpg').unlink()
        self.assertEqual(self.call('/api/avatars/sample?id='+avatar_id)[0],400)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ConfigStore(self.directory.name)
        self.server = create_server(self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_port
        self.addCleanup(self.stop)
        self.token = self.call('/api/session')[1]['token']

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def call(self, path, value=None, **headers):
        if value is not None:
            headers = {'Origin': self.base, 'Content-Type': 'application/json',
                       'X-Console-Token': getattr(self, 'token', ''), **headers}
        req = Request(self.base + path, data=None if value is None else json.dumps(value).encode(), headers=headers)
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_product_fact_edit_requires_valid_expiry_and_preserves_version(self):
        base = dict(title='测试商品', content='原说明', product_index=8)
        status, response = self.call('/api/products', base)
        self.assertEqual(status, 200)
        original = response['product']
        facts = {'price': {'value': 100, 'status': 'verified', 'source': 'catalog',
                           'expires_at': '2026-12-01T00:00:00'}}
        update = dict(base, product_id=original['id'], version=original['version'],
                      product_facts=facts)
        self.assertEqual(self.call('/api/products', update)[0], 400)
        self.assertEqual(self.call('/api/products')[1]['products'][0]['version'], original['version'])
        facts['price']['expires_at'] += 'Z'
        self.assertEqual(self.call('/api/products', update)[0], 200)
        saved = self.call('/api/products')[1]['products'][0]
        self.assertEqual(saved['version'], original['version'] + 1)
        self.assertEqual(saved['extra']['product_facts'], facts)
        self.assertEqual(self.call('/api/products', update)[0], 409)

    def test_session_reports_configured_speech_engine(self):
        self.assertEqual(self.call('/api/session')[1]['tts_engine'], 'indextts')
        for engine in ('zipvoice', 'omnivoice'):
            with self.subTest(engine=engine):
                server = create_server(self.store, port=0, tts_engine=engine)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                try:
                    url = f'http://127.0.0.1:{server.server_port}/api/session'
                    with urlopen(url, timeout=3) as response:
                        self.assertEqual(json.load(response)['tts_engine'], engine)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()

    def test_refresh_does_not_create_config_or_live_session(self):
        for _ in range(3):
            status, value = self.call('/api/state')
            self.assertEqual(status, 200)
            self.assertEqual(value['live_status'], '未启动')
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_save_reload_and_read_only_preflight(self):
        config = {'version': 1, 'runtime_root': self.directory.name, 'port': 5168}
        self.assertEqual(self.call('/api/config', config)[0], 200)
        self.assertEqual(self.call('/api/state')[1]['config'], config)
        self.assertEqual(self.call('/api/preflight', config)[1]['ready'], False)
        self.assertEqual([p.name for p in Path(self.directory.name).iterdir()], ['console.json'])

    def test_cross_origin_token_and_host_checks(self):
        config = self.store.load()
        for headers in ({'Origin': 'https://example.com'}, {'X-Console-Token': 'bad'}, {'Host':'example.com'}):
            self.assertEqual(self.call('/api/config', config, **headers)[0], 403)
        self.assertFalse(self.store.path.exists())

    def test_corrupt_state_visible_and_can_be_explicitly_repaired(self):
        self.store.path.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.call('/api/state')[0], 400)
        self.assertEqual(self.store.path.read_text(), '{broken')
        self.assertEqual(self.call('/api/config', {'version':1,'runtime_root':'','port':5158})[0], 200)

    def test_static_and_unknown_paths(self):
        with urlopen(self.base + '/', timeout=3) as response:
            self.assertIn('数字人工作台', response.read().decode())
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
            self.assertIn("media-src 'self' blob:", response.headers['Content-Security-Policy'])
        self.assertEqual(self.call('/console.json')[0], 404)

    def test_shutdown_requires_explicit_request_and_stops_server(self):
        self.assertEqual(self.call('/api/shutdown', {})[0], 400)
        self.assertEqual(self.call('/api/state')[0], 200)
        self.assertEqual(self.call('/api/shutdown', {'confirm': True})[0], 200)
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())

    def test_os_lock_rejects_second_process_and_releases(self):
        code = ('from scripts.local_console import InstanceLock; '
                'import sys; lock=InstanceLock(sys.argv[1]); lock.__enter__(); lock.__exit__()')
        with InstanceLock(self.directory.name):
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code, self.directory.name],
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
        result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code, self.directory.name],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_port_conflict_does_not_disrupt_existing_service(self):
        with self.assertRaises(OSError):
            create_server(self.store, port=self.server.server_port)
        self.assertEqual(self.call('/api/state')[0], 200)

    def test_product_edit_selection_scripts_and_conflict(self):
        def create(index, name):
            status, value = self.call('/api/products', {'title': name, 'content': name + '商品信息', 'product_index': index})
            self.assertEqual(status, 200)
            return value['product']
        a, b = create('008', '茶杯'), create(3, '毛巾')
        self.assertEqual(self.call('/api/products/select', {'product_id':a['id']})[0], 200)
        self.assertEqual(self.call('/api/products')[1]['selected'], a['id'])
        self.assertEqual(self.call('/api/scripts', {'snapshot':a, 'text':'茶杯话术{助：补充一句}{停:1.5}'})[0], 201)
        self.assertEqual(self.call('/api/scripts?product_id=' + b['id'])[1]['scripts'], [])
        update = {'product_id':a['id'], 'version':a['version'], 'title':a['title'],
                  'content':'容量更新', 'product_index':a['product_index']}
        self.assertEqual(self.call('/api/products', update)[0], 200)
        self.assertEqual(self.call('/api/products', update)[0], 409)
        self.assertEqual(self.call('/api/scripts', {'snapshot':a, 'text':'过期话术'})[0], 409)
        self.assertEqual(len(self.call('/api/scripts?product_id=' + a['id'])[1]['scripts']), 1)
        latest=self.call('/api/products')[1]['products'][0]
        original=self.call('/api/scripts?product_id=' + a['id'])[1]['scripts'][0]
        self.assertEqual(original['segments'], [
            {'type': 'host', 'content': '茶杯话术'},
            {'type': 'assistant', 'content': '补充一句'},
            {'type': 'pause', 'duration': 1.5},
        ])
        self.assertEqual(self.call('/api/scripts',{'snapshot':latest,'text':'修改话术','parent_script_id':original['id']})[0],201)
        self.assertEqual(self.call('/api/scripts',{'snapshot':b,'text':'串商品稿','parent_script_id':original['id']})[0],400)
        records=self.call('/api/scripts?product_id='+a['id'])[1]['scripts']
        self.assertEqual(self.call('/api/scripts/select',{'product_id':a['id'],'script_id':records[-1]['id']})[0],200)
        self.assertEqual(self.call('/api/scripts?product_id='+a['id'])[1]['selected'],records[-1]['id'])
        self.assertEqual(self.call('/api/scripts/select',{'product_id':a['id'],'script_id':original['id']})[0],409)

    def test_invalid_product_requests_visible(self):
        for path, value in [('/api/products', {}), ('/api/products/select', {}), ('/api/scripts', {}),
                            ('/api/products', {'title':'', 'content':'x', 'product_index':1})]:
            self.assertEqual(self.call(path, value)[0], 400)
        self.assertEqual(self.call('/api/scripts')[0], 400)

    def test_llm_missing_configuration_is_visible_without_creating_task(self):
        with patch.dict(os.environ, {'SHUZIREN_LLM_API_KEY':''}):
            status, value = self.call('/api/llm/state')
            self.assertEqual(status,200)
            self.assertFalse(value['configured'])
            p=self.call('/api/products', {'title':'茶杯','content':'300毫升','product_index':8})[1]['product']
            status, value=self.call('/api/llm/generate', {'product_id':p['id'],'version':1,'instructions':''})
            self.assertEqual(status,400)
            self.assertIn('尚未配置',value['error'])
            self.assertIsNone(self.call('/api/llm/state')[1]['task'])

    def test_tts_state_and_audio_require_valid_task_and_selected_inputs(self):
        self.store.save({'version':1,'runtime_root':self.directory.name,'port':5158})
        self.assertEqual(self.call('/api/tts/state')[1]['task'],None)
        self.assertEqual(self.call('/api/tts/audio?task_id=../console.json')[0],409)
        self.assertEqual(self.call('/api/tts/generate',{})[0],400)
        self.assertEqual(self.call('/api/tts/generate',{'product_id':'missing','script_id':'missing',
            'voice_id':'missing','speed':1,'language':'zh-CN','use_cache':False})[0],400)
        self.assertIsNone(self.call('/api/tts/state')[1]['task'])

    def test_voice_import_selection_audio_and_invalid_id(self):
        ffmpeg=os.environ.get('SHUZIREN_TEST_FFMPEG')
        if not ffmpeg or not Path(ffmpeg).is_file(): self.skipTest('Explicit real runtime FFmpeg required')
        runtime=Path(ffmpeg).parents[4]
        self.store.save({'version':1,'runtime_root':str(runtime),'port':5158})
        source=Path(self.directory.name)/'reference.wav'
        with wave.open(str(source),'wb') as output:
            output.setparams((1,2,24000,0,'NONE','not compressed'))
            output.writeframes((b'\x88\x13\x78\xec')*24000)
        status,value=self.call('/api/voices/import',{'source':str(source),'transcript':'媒体测试音，不是语音','name':'测试音色'})
        self.assertEqual(status,201,value)
        voice_id=value['voice']['id']
        self.assertEqual(self.call('/api/voices/select',{'voice_id':voice_id})[0],200)
        self.assertEqual(self.call('/api/voices')[1]['selected'],voice_id)
        with urlopen(self.base+'/api/voices/audio?id='+voice_id,timeout=3) as response:
            self.assertEqual(response.headers['Content-Type'],'audio/wav')
            self.assertEqual(response.read(4),b'RIFF')
        self.assertEqual(self.call('/api/voices/audio?id=../console.json')[0],400)
        self.assertEqual(self.call('/api/voices/import',{'source':str(source),'transcript':'','name':'测试'})[0],400)
        self.assertEqual(self.call('/api/voices/recorded',{'audio_base64':base64.b64encode(source.read_bytes()).decode(),
            'transcript':'录音传输测试音','name':'录音传输测试'})[0],201)
        self.assertEqual(self.call('/api/voices/recorded',{'audio_base64':'not-base64!',
            'transcript':'测试','name':'坏录音'})[0],400)
        self.assertEqual(list((Path(self.directory.name)/'voices').glob('recording-*.webm')),[])


if __name__ == '__main__':
    unittest.main()
