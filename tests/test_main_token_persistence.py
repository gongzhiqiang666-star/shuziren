from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from recovered.main import Api
from recovered.main_config import load_user_config


class MainTokenPersistenceTests(unittest.TestCase):
    def api(self, token="old"):
        api = Api.__new__(Api)
        api.config = {"token": token, "other": "preserved"}
        api._digital_live_manager = SimpleNamespace(config=None)
        api._record_live_manager = SimpleNamespace(config=None)
        api._face_hand_live_manager = SimpleNamespace(config=None)
        return api

    def test_save_and_clear_round_trip_exact_value(self):
        with tempfile.TemporaryDirectory() as directory:
            user = Path(directory) / "user_config.yaml"
            api = self.api()
            with patch.object(api, "_resolve_user_config_path", return_value=str(user)):
                self.assertEqual(api.save_token("  exact token  ")["status"], "success")
                self.assertEqual(load_user_config(user), {"token": "  exact token  "})
                for manager in (api._digital_live_manager, api._record_live_manager,
                                api._face_hand_live_manager):
                    self.assertIs(manager.config, api.config)
                self.assertEqual(api.clear_token()["status"], "success")
            self.assertEqual(load_user_config(user), {"token": ""})
            self.assertEqual(api.get_token()["token"], "")

    def test_rejected_or_failed_save_preserves_memory_and_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            user = Path(directory) / "user_config.yaml"
            api = self.api()
            with patch.object(api, "_resolve_user_config_path", return_value=str(user)):
                self.assertEqual(api.save_token("old")["status"], "success")
                self.assertIn("长度", api.save_token("x" * (Api._TOKEN_MAX_CHARS + 1))["error"])
                self.assertEqual(api.config["token"], "old")
                self.assertEqual(load_user_config(user)["token"], "old")
                with patch.object(api, "_save_user_config", side_effect=PermissionError("read only")):
                    result = api.save_token("secret-must-not-appear")
                self.assertEqual(result, {"error": "read only"})
            self.assertEqual(api.config["token"], "old")
            self.assertEqual(load_user_config(user)["token"], "old")
            self.assertNotIn("secret-must-not-appear", str(result))


if __name__ == "__main__":
    unittest.main()
