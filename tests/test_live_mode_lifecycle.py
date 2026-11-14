import unittest

from recovered.main import Api


class _Manager:
    def __init__(self, *, result=True, error=None, last_error=None):
        self.is_broadcasting = True
        self.result = result
        self.error = error
        self.last_error = last_error
        self.stops = 0

    def stop_live(self):
        self.stops += 1
        self.is_broadcasting = False
        if self.error:
            raise self.error
        return self.result


class LiveModeLifecycleTests(unittest.TestCase):
    def test_first_stop_failure_does_not_skip_other_live_modes(self):
        api = Api.__new__(Api)
        face = _Manager(result=False, last_error="face stop failed")
        record = _Manager()
        digital = _Manager()
        api._face_hand_live_manager = face
        api._record_live_manager = record
        api._digital_live_manager = digital

        result = api._stop_live_locked()

        self.assertEqual(result, {"status": "error", "message": "face stop failed"})
        self.assertEqual((face.stops, record.stops, digital.stops), (1, 1, 1))

    def test_stop_exception_is_stable_and_later_modes_are_released(self):
        api = Api.__new__(Api)
        face = _Manager(error=OSError("face close crashed"))
        record = _Manager(result=False, last_error="record stop failed")
        digital = _Manager()
        api._face_hand_live_manager = face
        api._record_live_manager = record
        api._digital_live_manager = digital

        result = api._stop_live_locked()

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "face close crashed")
        self.assertEqual((face.stops, record.stops, digital.stops), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
