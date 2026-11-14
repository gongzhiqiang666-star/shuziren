import tempfile
from pathlib import Path
import unittest

import cv2
import numpy as np

from recovered.product_cutout import _compose_centered_bgra
from recovered.product_kt_overlay import (
    ProductKtOverlay, _paste_on_board, load_kt_board_cache, save_kt_board_cache,
)


class ProductVisualToolTests(unittest.TestCase):
    def test_transparent_cutout_preserves_soft_alpha(self):
        rgb = np.zeros((20, 30, 3), np.uint8)
        rgb[..., 0] = 220
        mask = np.zeros((20, 30), np.uint8)
        mask[4:16, 6:24] = 255
        mask[3, 6:24] = 96
        output = _compose_centered_bgra(rgb, mask, canvas=100, fill=.8)
        self.assertEqual(output.shape, (100, 100, 4))
        self.assertEqual(int(output[0, 0, 3]), 0)
        self.assertGreater(int(output[..., 3].max()), 250)
        self.assertTrue(np.any((output[..., 3] > 0) & (output[..., 3] < 255)))

    def test_kt_overlay_alpha_blends_and_keeps_aspect_ratio(self):
        frame = np.full((120, 160, 3), 40, np.uint8)
        product = np.zeros((20, 40, 4), np.uint8)
        product[..., 2] = 240
        product[..., 3] = 128
        box = np.float32([[20, 10], [140, 10], [140, 110], [20, 110]])
        output = _paste_on_board(frame, product, box)
        changed = np.any(output != frame, axis=2)
        ys, xs = np.where(changed)
        self.assertGreater(len(xs), 0)
        self.assertGreater((xs.max() - xs.min()) / (ys.max() - ys.min()), 1.5)
        self.assertTrue(np.all(output[0, 0] == frame[0, 0]))
        center = output[60, 80]
        self.assertGreater(int(center[2]), 120)
        self.assertGreater(int(center[0]), 10)

    def test_local_transparent_png_is_not_flattened(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'product.png'
            image = np.zeros((12, 16, 4), np.uint8)
            image[..., 1] = 200
            image[..., 3] = 77
            self.assertTrue(cv2.imwrite(str(path), image))
            overlay = ProductKtOverlay()
            overlay.set_product_image(goods_id=1, item_pic=str(path))
            self.assertEqual(overlay._product.shape, (12, 16, 4))
            self.assertEqual(int(overlay._product[0, 0, 3]), 77)
            path.unlink()
            overlay.set_product_image(goods_id=1, item_pic=str(path))
            self.assertIsNotNone(overlay._product)

    def test_kt_cache_round_trip_and_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            box = np.float32([[1, 2], [9, 2], [9, 8], [1, 8]])
            path = Path(save_kt_board_cache(directory, [box, None], (10, 12), 1))
            boxes, size, hit = load_kt_board_cache(directory)
            self.assertTrue(np.array_equal(boxes[0], box))
            self.assertIsNone(boxes[1])
            self.assertEqual((size, hit), ((10, 12), 1))
            with path.open('wb') as stream:
                np.savez_compressed(stream, boxes=np.zeros((1, 3, 2)), valid=np.ones(1),
                                    frame_size=np.array((10, 12)), hit=np.array(1))
            with self.assertRaisesRegex(ValueError, 'shape'):
                load_kt_board_cache(directory)


if __name__ == '__main__':
    unittest.main()
