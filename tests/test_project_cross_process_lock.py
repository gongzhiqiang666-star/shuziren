import multiprocessing
import tempfile
import unittest
from pathlib import Path

from recovered.main import Api


class _TestApi(Api):
    def _get_ip_agent_base_dir(self):
        return str(Path(self.runtime_dir) / "assets" / "ip_agent_projects")


def _api(root):
    api = object.__new__(_TestApi)
    api.runtime_dir = Path(root)
    api.base_dir = str(root)
    api.config = {}
    api._ip_publish_active = set()
    return api


def _save_field(kind, root, project_id, field, value, result_queue):
    try:
        api = _api(root)
        if kind == "ip":
            api._save_ip_agent_project(project_id, {field: value})
        elif kind == "sticker":
            api._save_live_sticker_project(project_id, {field: value})
        else:
            api._save_cloud_dh_project(project_id, {field: value})
        result_queue.put(None)
    except BaseException as error:
        result_queue.put(repr(error))


def _late_cloud_save(root, project_id, ready, release, result_queue):
    try:
        api = _api(root)
        stale = api._load_cloud_dh_project(project_id)
        ready.set()
        if not release.wait(10):
            raise TimeoutError("late writer was not released")
        api._save_cloud_dh_project(project_id, {**stale, "late": True})
        result_queue.put("unexpected_success")
    except BaseException as error:
        result_queue.put(repr(error))


class ProjectCrossProcessLockTests(unittest.TestCase):
    def _exercise(self, kind):
        with tempfile.TemporaryDirectory() as directory:
            api = _api(directory)
            project_id = "shared-project"
            if kind == "ip":
                Path(api._get_ip_agent_project_dir(project_id)).mkdir(parents=True)
                api._save_ip_agent_project(project_id, {"name": "跨进程IP"})
                load = api._load_ip_agent_project
            elif kind == "sticker":
                Path(api._get_live_sticker_project_dir(project_id)).mkdir(parents=True)
                api._save_live_sticker_project(project_id, {"name": "跨进程贴片"})
                load = api._load_live_sticker_project
            else:
                api._save_cloud_dh_project(project_id, {"name": "跨进程云数字人"})
                load = api._load_cloud_dh_project

            context = multiprocessing.get_context("spawn")
            results = context.Queue()
            processes = [context.Process(
                target=_save_field,
                args=(kind, directory, project_id, f"worker_{index}", index, results),
            ) for index in range(8)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(20)
                self.assertFalse(process.is_alive(), "project writer did not exit")
                self.assertEqual(process.exitcode, 0)
            errors = [results.get(timeout=2) for _ in processes]
            self.assertEqual(errors, [None] * len(processes))
            saved = load(project_id)
            self.assertEqual({saved[f"worker_{index}"] for index in range(8)}, set(range(8)))
            self.assertFalse(any(Path(directory).rglob("*.pending")))

    def test_ip_project_cross_process_updates_are_merged(self):
        self._exercise("ip")

    def test_sticker_project_cross_process_updates_are_merged(self):
        self._exercise("sticker")

    def test_cloud_project_cross_process_updates_are_merged(self):
        self._exercise("cloud")

    def test_deleted_projects_cannot_be_resurrected_by_late_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            api = _api(directory)
            project_id = "deleted-project"

            Path(api._get_ip_agent_project_dir(project_id)).mkdir(parents=True)
            api._save_ip_agent_project(project_id, {"name": "待删除IP"})
            self.assertEqual(api.delete_ip_agent_project(project_id)["status"], "success")
            self.assertIn("error", api.update_ip_agent_project(project_id, {"late": True}))
            self.assertFalse(Path(api._get_ip_agent_project_dir(project_id)).exists())

            Path(api._get_live_sticker_project_dir(project_id)).mkdir(parents=True)
            api._save_live_sticker_project(project_id, {"name": "待删除贴片"})
            self.assertEqual(api.delete_live_sticker_project(project_id)["status"], "success")
            self.assertIn("error", api.update_live_sticker_project(project_id, {"late": True}))
            self.assertFalse(Path(api._get_live_sticker_project_dir(project_id)).exists())

            api._save_cloud_dh_project(project_id, {"name": "待删除云数字人"})
            self.assertEqual(api.delete_cloud_dh_project(project_id)["status"], "success")
            self.assertEqual(api.update_cloud_dh_project(project_id, {"late": True})["status"], "error")
            with self.assertRaises(FileNotFoundError):
                api._save_cloud_dh_project(project_id, {"late": True})
            self.assertFalse(Path(api._get_cloud_dh_project_dir(project_id)).exists())

    def test_cloud_project_rejects_cross_process_stale_save_after_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            api = _api(directory)
            project_id = "stale-cloud-project"
            api._save_cloud_dh_project(project_id, {"name": "跨进程删除"})
            context = multiprocessing.get_context("spawn")
            ready, release = context.Event(), context.Event()
            results = context.Queue()
            process = context.Process(
                target=_late_cloud_save,
                args=(directory, project_id, ready, release, results),
            )
            process.start()
            self.assertTrue(ready.wait(10), "late writer did not read the project")
            self.assertEqual(api.delete_cloud_dh_project(project_id)["status"], "success")
            release.set()
            process.join(20)
            self.assertFalse(process.is_alive(), "late writer did not exit")
            self.assertEqual(process.exitcode, 0)
            self.assertIn("FileNotFoundError", results.get(timeout=2))
            self.assertFalse(Path(api._get_cloud_dh_project_dir(project_id)).exists())


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
