import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from recovered import runninghub_hold as hold


class Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class RunningHubHoldTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.avatar = self.root / "avatar.png"
        self.product = self.root / "product.jpg"
        self.avatar.write_bytes(b"avatar-image")
        self.product.write_bytes(b"product-image")

    def test_request_plan_has_fingerprints_and_no_secret(self):
        plan = hold.request_plan(avatar=self.avatar, product=self.product, product_name="青瓷杯")
        self.assertEqual((plan["engine"], plan["webapp_id"]),
                         ("qwen21", "2113900488247824386"))
        self.assertEqual([item["role"] for item in plan["uploads"]], ["avatar", "product"])
        self.assertTrue(all(len(item["sha256"]) == 64 for item in plan["uploads"]))
        self.assertIn("青瓷杯", plan["prompt"])
        self.assertNotIn("api_key", repr(plan).lower())
        foreign = self.root / "audio.wav"
        foreign.write_bytes(b"not-image")
        with self.assertRaisesRegex(ValueError, "格式无效"):
            hold.request_plan(avatar=foreign, product=self.product)

    def test_submit_matches_v179_qwen21_workflow_contract(self):
        response = Response({"code": 0, "data": {"taskId": "task-1"}})
        with patch.object(hold.requests, "post", return_value=response) as post:
            task_id = hold.submit_hold_task(api_key="request-only-key", avatar_remote="avatar.png",
                                            product_remote="product.png", prompt="prompt")
        self.assertEqual(task_id, "task-1")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://www.runninghub.cn/task/openapi/ai-app/run")
        payload = kwargs["json"]
        self.assertEqual((payload["webappId"], payload["instanceType"], payload["retainSeconds"]),
                         ("2113900488247824386", "default", 20))
        self.assertEqual([(item["nodeId"], item["fieldName"], item["fieldValue"])
                          for item in payload["nodeInfoList"]], [
            ("37", "image", "avatar.png"), ("63", "image", "product.png"),
            ("33", "aspect_ratio", "9:16 (Portrait Widescreen)"),
            ("33", "megapixels", "1"), ("32", "text", "prompt"),
        ])

    def test_query_and_generation_lifecycle_support_cancel_and_success(self):
        response = Response({"code": 0, "data": {"status": "SUCCESS", "outputs": [
            {"fileUrl": "https://example.test/held.png"}]}})
        with patch.object(hold.requests, "post", return_value=response):
            self.assertEqual(hold.query_hold_task(api_key="key", task_id="task")["status"], "success")

        output = self.root / "held.png"
        with (patch.object(hold, "upload_file", side_effect=["avatar.remote", "product.remote"]) as upload,
              patch.object(hold, "submit_hold_task", return_value="task") as submit,
              patch.object(hold, "query_hold_task", return_value={
                  "task_id": "task", "status": "success", "image_url": "https://example.test/held.png",
                  "fail_reason": ""}),
              patch.object(hold, "download_image", side_effect=lambda _url, dest: Path(dest).resolve())):
            result = hold.generate_hold_image(api_key="key", avatar=self.avatar, product=self.product,
                                              dest=output, poll_interval=0)
        self.assertEqual(result["image_path"], str(output.resolve()))
        self.assertEqual(upload.call_args_list, [
            call(api_key="key", file_path=str(self.avatar.resolve())),
            call(api_key="key", file_path=str(self.product.resolve())),
        ])
        submit.assert_called_once()

        with patch.object(hold, "upload_file") as upload:
            with self.assertRaisesRegex(InterruptedError, "已取消"):
                hold.generate_hold_image(api_key="key", avatar=self.avatar, product=self.product,
                                         dest=output, cancel_check=lambda: True)
            upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
