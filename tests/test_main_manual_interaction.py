import threading
import unittest

from recovered.main import Api


class Manager:
    def __init__(self, broadcasting=False, accepted=True):
        self.is_broadcasting = broadcasting
        self.accepted = accepted
        self.last_error = "管理器拒绝"
        self.manual = []
        self.questions = []

    def request_manual_speak(self, text):
        self.manual.append(text)
        return self.accepted

    def request_simulated_question(self, text):
        self.questions.append(text)
        return self.accepted


class ManualInteractionTests(unittest.TestCase):
    def api(self, digital=False, face=False):
        api = object.__new__(Api)
        api._live_lifecycle_lock = threading.RLock()
        api._digital_live_manager = Manager(digital)
        api._face_hand_live_manager = Manager(face)
        return api

    def test_digital_live_accepts_manual_speech_and_question(self):
        api = self.api(digital=True)
        self.assertEqual(api.speak("立即播报"), {"status": "success"})
        self.assertEqual(api.simulate_question("这个怎么用"), {"status": "success"})
        self.assertEqual(api._digital_live_manager.manual, ["立即播报"])
        self.assertEqual(api._digital_live_manager.questions, ["这个怎么用"])

    def test_face_hand_live_routes_to_its_active_manager(self):
        api = self.api(face=True)
        self.assertEqual(api.speak("人脸人手口播"), {"status": "success"})
        self.assertEqual(api.simulate_question("模拟问题"), {"status": "success"})
        self.assertEqual(api._face_hand_live_manager.manual, ["人脸人手口播"])
        self.assertEqual(api._face_hand_live_manager.questions, ["模拟问题"])
        self.assertEqual(api._digital_live_manager.manual, [])

    def test_stopped_invalid_and_rejected_requests_return_actionable_errors(self):
        api = self.api()
        self.assertIn("开启直播", api.speak("内容")["message"])
        self.assertIn("播报内容", api.speak("  ")["message"])
        self.assertIn("开启直播", api.simulate_question("问题")["message"])
        api._digital_live_manager.is_broadcasting = True
        api._digital_live_manager.accepted = False
        self.assertEqual(api.speak("内容")["message"], "管理器拒绝")
        self.assertIn("有效的问题", api.simulate_question("问题")["message"])


if __name__ == "__main__":
    unittest.main()
