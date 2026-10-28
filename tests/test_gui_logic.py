"""Regression checks for completion reporting without creating any Tk window."""
import unittest

from moonalign.gui import MoonAlignApp


class _Variable:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class _Widget:
    def __init__(self):
        self.values = {}

    def configure(self, **kwargs):
        self.values.update(kwargs)


class _FakeApp:
    """Only the attributes used by _finish; no Tk, Tcl, or widget instances."""
    def __init__(self):
        self.progress = _Widget()
        self.progress_var = _Variable()
        self.counts_var = _Variable()
        self.frames_button = _Widget()
        self.reports_button = _Widget()
        self.stage_var = _Variable()
        self._close_requested = False
        self.logs = []
        self.busy = None
        self.destroyed = False

    def _set_busy(self, value):
        self.busy = value

    def _append_log(self, message, tag=""):
        self.logs.append((message, tag))

    def _destroy(self):
        self.destroyed = True


class FinishLogicTests(unittest.TestCase):
    def finish(self, summary):
        app = _FakeApp()
        MoonAlignApp._finish(app, summary)
        self.assertIs(app.busy, False)
        return app

    @staticmethod
    def completed(**changes):
        summary = {"status": "completed", "total": 2, "success": 2,
                   "failed": 0, "passed": True}
        summary.update(changes)
        return summary

    def assert_audit_failure(self, summary):
        app = self.finish(summary)
        self.assertIn("最终检查未通过", app.stage_var.value)
        self.assertIn("暂勿导入 AS", app.stage_var.value)
        self.assertEqual(app.logs[0][1], "error")
        self.assertFalse(any(tag == "success" for _, tag in app.logs))
        return app

    def test_completed_passing_job_reports_success(self):
        app = self.finish(self.completed())
        self.assertIn("对齐完成", app.stage_var.value)
        self.assertEqual(app.logs[0][1], "success")
        self.assertEqual(app.progress_var.value, "2 / 2")
        self.assertEqual(app.counts_var.value, "成功 2    失败 0")

    def test_passed_false_cannot_report_success(self):
        self.assert_audit_failure(self.completed(passed=False))

    def test_audit_passed_false_cannot_report_success(self):
        self.assert_audit_failure(self.completed(audit_passed=False))

    def test_missing_passed_is_not_assumed_successful(self):
        summary = self.completed()
        del summary["passed"]
        self.assert_audit_failure(summary)

    def test_audit_problem_files_override_inconsistent_passed_true(self):
        app = self.assert_audit_failure(self.completed(audit_problem_files=["a.tif"]))
        self.assertTrue(any("a.tif" in line for line, _ in app.logs))

    def test_source_changes_override_inconsistent_passed_true(self):
        app = self.assert_audit_failure(self.completed(
            source_files_changed_by_size_or_mtime=["a.tif"]))
        self.assertTrue(any("a.tif" in line for line, _ in app.logs))

    def test_cancelled_job_reports_partial_progress(self):
        app = self.finish({"status": "cancelled", "total": 2, "success": 1,
                           "failed": 0, "passed": False, "cancelled": True})
        self.assertIn("已停止", app.stage_var.value)
        self.assertNotIn("最终检查未通过", app.stage_var.value)
        self.assertEqual(app.progress_var.value, "1 / 2")
        self.assertEqual(app.logs[0][1], "")

    def test_pilot_failure_does_not_claim_full_processing(self):
        app = self.finish({"status": "pilot_failed", "total": 2, "success": 1,
                           "failed": 1, "passed": False})
        self.assertIn("小批验证未通过", app.stage_var.value)
        self.assertIn("尚未开始全量", app.stage_var.value)
        self.assertEqual(app.logs[0][1], "error")

    def test_pending_close_is_applied_after_worker_completion(self):
        app = _FakeApp()
        app._close_requested = True
        self.assertFalse(app.destroyed)
        MoonAlignApp._finish(app, {"status": "cancelled", "total": 2,
            "success": 1, "failed": 0, "cancelled": True})
        self.assertTrue(app.destroyed)


if __name__ == "__main__":
    unittest.main()
