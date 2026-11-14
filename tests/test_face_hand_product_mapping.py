import unittest

from recovered.face_hand_live_manager import FaceHandLiveManager


class _Popup:
    def __init__(self):
        self.shown = []

    def show_product(self, **kwargs):
        self.shown.append(kwargs)


class FaceHandProductMappingTests(unittest.TestCase):
    def test_explicit_product_index_selects_matching_image(self):
        manager = FaceHandLiveManager({})
        products = [
            {
                "product_index": 7,
                "itemId": "700",
                "itemName": "七号商品",
                "itemPic": "//img.example/7.png",
            },
            {
                "product_index": "bad",
                "itemId": "101",
                "itemName": "顺序商品",
                "itemPic": "https://img.example/1.png",
            },
        ]
        manager.product_image_items = manager._build_product_image_items(products)
        manager._product_image_index_map = manager._build_product_image_index_map(products)
        manager._live_config = {"enable_product_image_sync": True}
        manager._product_popup = _Popup()

        manager._sync_product_image(7)
        manager._sync_product_image(1)

        self.assertEqual(
            [item["goods_id"] for item in manager._product_popup.shown],
            [700, 101],
        )
        self.assertEqual(
            manager.product_image_items[0]["itemPic"],
            "https://img.example/7.png",
        )
        manager._interaction_llm_executor.shutdown(wait=True)

    def test_unknown_product_index_does_not_show_wrong_item(self):
        manager = FaceHandLiveManager({})
        products = [
            {"product_index": 5, "itemId": "5", "itemName": "五号商品"}
        ]
        manager.product_image_items = manager._build_product_image_items(products)
        manager._product_image_index_map = manager._build_product_image_index_map(products)
        manager._live_config = {"enable_product_image_sync": True}
        manager._product_popup = _Popup()

        manager._sync_product_image(99)

        self.assertEqual(manager._product_popup.shown, [])
        manager._interaction_llm_executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
