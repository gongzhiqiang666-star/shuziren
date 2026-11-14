import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path

import cv2
import numpy as np

from recovered.digital_live_manager import DigitalLiveManager
from recovered.frame_player_kt import StreamPlayer
from recovered.product_kt_overlay import (
    close_product_kt_overlay, save_kt_board_cache,
)


class FakeOverlay:
    def __init__(self, hits=3):
        self.hits = hits
        self.actions = []

    def set_enabled(self, value): self.actions.append(('enabled', value))
    def clear(self): self.actions.append(('clear',))
    def load_from_model_dir(self, value): self.actions.append(('load', value)); return self.hits
    def set_product_image(self, **value): self.actions.append(('product', value))


class ProductKtLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.manager = DigitalLiveManager({}, '.')

    def test_script_items_keep_product_switch_identity(self):
        products = [
            {'goods_id': 11, 'item_pic': 'a.png', 'scripts': ['甲', '乙']},
            {'goods_id': 22, 'item_pic': 'b.png', 'scripts': ['丙']},
        ]
        items = self.manager._load_text_script_items({'product_scripts': products})
        self.assertEqual([item[0] for item in items], ['甲', '乙', '丙'])
        self.assertIs(items[0][1], products[0])
        self.assertIs(items[2][1], products[1])

    def test_prepare_loads_cache_product_and_enables_last(self):
        overlay = FakeOverlay()
        config = {'enable_product_kt_follow': True, 'products': [
            {'goodsId': '12', 'itemPic': 'product.png', 'title': '商品'}]}
        with patch('recovered.product_kt_overlay.get_product_kt_overlay', return_value=overlay), \
             patch('recovered.digital_model_paths.resolve_character_dir', return_value='avatar'):
            self.manager._prepare_kt_overlay(config, {'model_id': 'avatar-id'})
        self.assertEqual(overlay.actions[0:3], [('enabled', False), ('clear',), ('load', 'avatar')])
        self.assertEqual(overlay.actions[3][1]['goods_id'], 12)
        self.assertEqual(overlay.actions[-1], ('enabled', True))

    def test_missing_board_fails_without_enabling(self):
        overlay = FakeOverlay(hits=0)
        with patch('recovered.product_kt_overlay.get_product_kt_overlay', return_value=overlay), \
             patch('recovered.digital_model_paths.resolve_character_dir', return_value='avatar'):
            with self.assertRaisesRegex(ValueError, '没有识别到'):
                self.manager._prepare_kt_overlay({'enableProductKtFollow': True}, {'model_id': 'id'})
        self.assertNotIn(('enabled', True), overlay.actions)

    def test_product_switch_accepts_schema_aliases(self):
        overlay = FakeOverlay()
        with patch('recovered.product_kt_overlay.get_product_kt_overlay', return_value=overlay):
            self.manager._sync_kt_product({'itemId': '23', 'itemPic': 'next.png', 'name': '下一件'})
        self.assertEqual(overlay.actions[-1], ('product', {
            'goods_id': 23, 'item_pic': 'next.png', 'item_name': '下一件'}))

    def test_real_cache_product_apply_and_reopen(self):
        self.addCleanup(close_product_kt_overlay)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            avatar = root/'avatar'; (avatar/'frames').mkdir(parents=True)
            quad = np.float32([[10, 10], [110, 10], [110, 110], [10, 110]])
            save_kt_board_cache(avatar, [quad], (120, 120), 1)
            product_path = root/'product.png'
            product = np.zeros((20, 40, 4), np.uint8)
            product[..., 1] = 220; product[..., 3] = 160
            self.assertTrue(cv2.imwrite(str(product_path), product))
            manager = DigitalLiveManager({'image_base_dir': str(root)}, root)
            config = {'enable_product_kt_follow': True, 'products': [{
                'goods_id': 7, 'item_pic': str(product_path), 'scripts': ['话术']} ]}
            frame = np.full((120, 120, 3), 30, np.uint8)
            manager._prepare_kt_overlay(config, {'model_id': 'avatar'})
            player = StreamPlayer(120, 120)
            player._submit_video_frame(frame, 0)
            first = player.player._frame
            self.assertGreater(np.count_nonzero(first != frame), 0)
            close_product_kt_overlay()
            manager._prepare_kt_overlay(config, {'model_id': 'avatar'})
            player._submit_video_frame(frame, 0)
            second = player.player._frame
            self.assertTrue(np.array_equal(first, second))

    def test_feed_switches_product_before_speech(self):
        product = {'goods_id': 9, 'scripts': ['介绍']}
        waits = iter((False, True))
        self.manager._script_stop = type('Stop', (), {
            'wait': lambda _self, _timeout: next(waits), 'is_set': lambda _self: False})()
        runtime = type('Runtime', (), {
            'get_queue_lengths': lambda _self: {'normal': 0},
            'add_audio_to_queue': lambda _self, value: setattr(_self, 'audio', value),
        })()
        with patch.object(self.manager, '_sync_kt_product') as sync, \
             patch.object(self.manager, '_synthesize', return_value='speech.wav') as synthesize:
            self.manager._feed_script_audio(runtime, [('介绍', product)], {})
        sync.assert_called_once_with(product)
        synthesize.assert_called_once_with({}, '介绍')
        self.assertEqual(runtime.audio, 'speech.wav')


if __name__ == '__main__':
    unittest.main()
