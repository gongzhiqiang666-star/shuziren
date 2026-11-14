import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.hold_product_tasks import HoldProductError, HoldProductTasks


class HoldProductTasksTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.avatar = self.root / "avatar.png"
        self.product = self.root / "product.jpg"
        self.avatar.write_bytes(b"avatar")
        self.product.write_bytes(b"product")

    def _wait(self, manager, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = manager.state()
            if state["status"] != "running":
                return state
            time.sleep(.01)
        self.fail("手持商品任务未结束")

    def test_success_owns_inputs_does_not_persist_key_and_verifies_output(self):
        def provider(**kwargs):
            output = Path(kwargs["dest"])
            self.assertTrue(Path(kwargs["avatar"]).is_file())
            self.assertTrue(Path(kwargs["product"]).is_file())
            output.write_bytes(b"generated-image")
            return {"task_id": "provider-1", "image_path": str(output)}

        with patch("scripts.hold_product_tasks.generate_hold_image", side_effect=provider):
            manager = HoldProductTasks(self.root / "data")
            self.addCleanup(manager.close)
            state = manager.start(api_key="secret-must-not-persist", avatar=self.avatar,
                                  product=self.product, product_name="青瓷杯")
            self.avatar.unlink()
            self.product.unlink()
            finished = self._wait(manager)
        self.assertEqual((finished["status"], finished["provider_task_id"]),
                         ("succeeded", "provider-1"))
        self.assertNotIn("secret-must-not-persist", manager.path.read_text(encoding="utf-8"))
        output = manager.output(state["id"])
        self.assertEqual([item.name for item in output.parent.iterdir()], ["held-product.png"])
        output.write_bytes(b"tampered")
        with self.assertRaisesRegex(HoldProductError, "已变化"):
            manager.output(state["id"])

    def test_cancel_failure_and_restart_cleanup_are_explicit(self):
        def blocked(**kwargs):
            while not kwargs["cancel_check"]():
                time.sleep(.01)
            raise InterruptedError("手持商品图生成已取消")

        with patch("scripts.hold_product_tasks.generate_hold_image", side_effect=blocked):
            manager = HoldProductTasks(self.root / "data")
            state = manager.start(api_key="key", avatar=self.avatar, product=self.product)
            manager.cancel(state["id"])
            self.assertEqual(self._wait(manager)["status"], "cancelled")
            self.assertFalse((manager.root / state["id"]).exists())
            manager.close()

        stale_id = "a" * 32
        stale = manager.root / stale_id
        stale.mkdir()
        (stale / "private-input.png").write_bytes(b"input")
        manager.path.write_text(json.dumps({"id": stale_id, "status": "running"}), encoding="utf-8")
        recovered = HoldProductTasks(self.root / "data")
        self.assertEqual(recovered.state()["status"], "interrupted")
        self.assertFalse(stale.exists())

        with patch("scripts.hold_product_tasks.generate_hold_image", side_effect=RuntimeError("provider failed")):
            failed = HoldProductTasks(self.root / "failed-data")
            state = failed.start(api_key="key", avatar=self.avatar, product=self.product)
            self.assertEqual(self._wait(failed)["status"], "failed")
            self.assertFalse((failed.root / state["id"]).exists())


if __name__ == "__main__":
    unittest.main()
