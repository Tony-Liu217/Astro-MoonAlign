"""Regression checks for completion reporting without creating any Tk window."""
import queue
import threading
import unittest
from unittest.mock import patch

from moonalign.gui import (MoonAlignApp, PERFORMANCE_MODES, _custom_resource_values,
                           _effective_memory_policy, _performance_text, _runtime_text)


class _Variable:
    def __init__(self, value=None):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _Widget:
    def __init__(self):
        self.values = {}

    def configure(self, **kwargs):
        self.values.update(kwargs)

    def __getitem__(self, key):
        return self.values.get(key)


class _FakeApp:
    """Only the attributes used by _finish; no Tk, Tcl, or widget instances."""
    def __init__(self):
        self.progress = _Widget()
        self.progress_var = _Variable()
        self.counts_var = _Variable()
        self.frames_button = _Widget()
        self.reports_button = _Widget()
        self.stage_var = _Variable()
        self.runtime_var = _Variable()
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

    def test_finished_runtime_reports_new_work_and_reused_frames_separately(self):
        app = self.finish(self.completed(elapsed_seconds=120, throughput_fps=5.25, resumed_frames=9))
        self.assertIn("2 分 0 秒", app.runtime_var.value)
        self.assertIn("新配准平均 5.25 张/秒", app.runtime_var.value)
        self.assertIn("已复用 9 张", app.runtime_var.value)


class ResourceFormattingTests(unittest.TestCase):
    def test_all_four_resource_modes_are_available(self):
        self.assertEqual(list(PERFORMANCE_MODES.values()), ["quiet", "balanced", "performance", "custom"])

    def test_resource_summary_uses_engine_values_and_labels_memory_as_estimate(self):
        text = _performance_text({"workers": 10, "compute_threads": 2,
            "estimated_memory_bytes": 4_200_000_000, "available_memory_bytes": 10_100_000_000})
        self.assertIn("10 张并发 × 2 线程/张", text)
        self.assertIn("4.2 GB", text)
        self.assertIn("10.1 GB", text)
        self.assertIn("估算", text)

    def test_custom_values_reject_incomplete_or_noninteger_input(self):
        self.assertEqual(_custom_resource_values("10", "2"), (10, 2))
        for values in (("", "2"), ("2.5", "1"), ("4", "")):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "应填写整数"):
                _custom_resource_values(*values)

    def test_expanded_policy_requires_custom_mode_and_explicit_opt_in(self):
        for mode in ("quiet", "balanced", "performance"):
            self.assertEqual(_effective_memory_policy(mode, True), "conservative")
        self.assertEqual(_effective_memory_policy("custom", False), "conservative")
        self.assertEqual(_effective_memory_policy("custom", True), "expanded")

    def test_policy_summary_shows_reserved_memory_and_selectable_workers(self):
        text = _performance_text({"workers": 5, "compute_threads": 2, "max_workers": 6,
            "memory_policy": "expanded", "reserved_memory_bytes": 1_100_000_000})
        self.assertIn("内存策略：放宽", text)
        self.assertIn("保留余量 1.1 GB", text)
        self.assertIn("可选并发 1～6", text)
        self.assertIn("内存策略：保守", _performance_text({"memory_policy": "conservative"}))

    def test_low_memory_engine_warning_is_visible_in_summary(self):
        text = _performance_text({"memory_sufficient": False})
        self.assertIn("可用内存不足", text)

    def test_registration_rate_and_eta_are_explicitly_separate_from_audit(self):
        text = _runtime_text({"stage": "all", "throughput_fps": 5.25, "eta_seconds": 125})
        self.assertIn("5.25 张/秒", text)
        self.assertIn("2 分 5 秒", text)
        self.assertIn("另需最终检查", text)

    def test_audit_never_displays_stale_registration_rate_or_eta(self):
        text = _runtime_text({"stage": "audit", "audit_done": 50, "audit_total": 100,
            "throughput_fps": 50, "eta_seconds": 999, "elapsed_seconds": 60})
        self.assertIn("最终检查 50/100", text)
        self.assertNotIn("张/秒", text)
        self.assertNotIn("预计剩余", text)

    def test_resume_does_not_invent_new_registration_throughput(self):
        text = _runtime_text({"stage": "pilot", "resumed_frames": 25, "throughput_fps": None})
        self.assertIn("已复用 25 张", text)
        self.assertIn("测量中", text)
        self.assertNotIn("张/秒", text)

    def test_initial_frames_wait_for_a_small_timing_sample(self):
        text = _runtime_text({"stage": "pilot", "processed_new": 1,
                              "throughput_fps": 30, "eta_seconds": 2})
        self.assertIn("测量中", text)
        self.assertNotIn("30.00", text)

    def test_missing_or_invalid_telemetry_does_not_show_nan_or_negative_eta(self):
        for speed in (None, 0, float("nan"), float("inf"), -5):
            with self.subTest(speed=speed):
                self.assertIn("测量中", _runtime_text({"throughput_fps": speed, "eta_seconds": 30}))
        text = _runtime_text({"throughput_fps": 5, "eta_seconds": -1})
        self.assertIn("预计剩余：测量中", text)
        self.assertNotIn("-1", text)


class _ResourceApp:
    def __init__(self, mode="均衡（推荐）", running=False):
        self.performance_mode_var = _Variable(mode)
        self.workers_var = _Variable("3")
        self.compute_threads_var = _Variable("1")
        self.expanded_memory_var = _Variable(False)
        self.resource_var = _Variable()
        self.performance_combo = _Widget()
        self.workers_spin = _Widget()
        self.compute_threads_spin = _Widget()
        self.memory_checkbox = _Widget()
        self._running = running
        self._performance_profile = None
        self._syncing_performance = False
        self.events = queue.Queue()
        self.selection_updated = False

    def _update_selection_label(self):
        self.selection_updated = True

    def _apply_performance_limits(self, profile):
        MoonAlignApp._apply_performance_limits(self, profile)

    def _update_performance_controls(self):
        MoonAlignApp._update_performance_controls(self)


class ResourceStateTests(unittest.TestCase):
    @staticmethod
    def profile(**changes):
        result = {"mode": "performance", "workers": 10, "compute_threads": 2,
                  "max_workers": 13, "max_compute_threads": 5, "logical_cpus": 20,
                  "estimated_memory_bytes": 4_200_000_000, "available_memory_bytes": 10_100_000_000}
        result.update(changes)
        return result

    def test_preset_uses_returned_limits_instead_of_old_six_worker_cap(self):
        app = _ResourceApp(mode="高性能")
        profile = self.profile()
        MoonAlignApp._apply_performance(app, profile)
        self.assertIs(app._performance_profile, profile)
        self.assertEqual(app.workers_var.get(), "10")
        self.assertEqual(app.compute_threads_var.get(), "2")
        self.assertEqual(app.workers_spin["to"], 13)
        self.assertEqual(app.compute_threads_spin["to"], 5)
        self.assertEqual(app.workers_spin["state"], "disabled")
        self.assertTrue(app.selection_updated)

    def test_custom_parameters_are_editable_only_when_idle(self):
        for mode, running, state in (("自定义", False, "normal"),
                                     ("自定义", True, "disabled"),
                                     ("均衡（推荐）", False, "disabled")):
            with self.subTest(mode=mode, running=running):
                app = _ResourceApp(mode, running)
                MoonAlignApp._update_performance_controls(app)
                self.assertEqual(app.workers_spin["state"], state)
                self.assertEqual(app.compute_threads_spin["state"], state)
                self.assertEqual(app.memory_checkbox["state"], state)
                self.assertEqual(app.performance_combo["state"], "disabled" if running else "readonly")

    def test_worker_queries_each_preset_without_overriding_engine_recommendations(self):
        for mode in ("quiet", "balanced", "performance"):
            with self.subTest(mode=mode), patch("moonalign.engine.get_performance_profile", return_value=self.profile()) as get_profile:
                app = _ResourceApp()
                MoonAlignApp._performance_worker(app, [2400, 2400], mode, "99", "99", 4, "expanded")
                get_profile.assert_called_once_with([2400, 2400], mode=mode, memory_policy="conservative")
                event = app.events.get_nowait()
                self.assertEqual(event[:2], ("performance", 4))

    def test_custom_worker_validates_limits_then_passes_exact_values(self):
        with patch("moonalign.engine.get_performance_profile", return_value=self.profile()) as get_profile:
            app = _ResourceApp()
            MoonAlignApp._performance_worker(app, [1800, 1800], "custom", "10", "2", 5)
            self.assertEqual(get_profile.call_count, 3)
            get_profile.assert_called_with([1800, 1800], mode="custom", workers=10, compute_threads=2,
                                           memory_policy="conservative")
            self.assertEqual(app.events.get_nowait()[:2], ("performance", 5))

    def test_expanded_custom_policy_is_used_for_limits_and_final_query(self):
        with patch("moonalign.engine.get_performance_profile", return_value=self.profile(memory_policy="expanded")) as get_profile:
            app = _ResourceApp(mode="自定义")
            MoonAlignApp._performance_worker(app, [1800, 1800], "custom", "5", "2", 5, "expanded")
            self.assertEqual(get_profile.call_count, 3)
            for call in get_profile.call_args_list:
                self.assertEqual(call.kwargs["memory_policy"], "expanded")
            get_profile.assert_called_with([1800, 1800], mode="custom", workers=5, compute_threads=2,
                                           memory_policy="expanded")

    def test_invalid_custom_input_returns_inline_error_without_tk(self):
        with patch("moonalign.engine.get_performance_profile", return_value=self.profile()):
            app = _ResourceApp()
            MoonAlignApp._performance_worker(app, None, "custom", "", "2", 6)
            event = app.events.get_nowait()
            self.assertEqual(event[:2], ("performance_error", 6))
            self.assertIn("应填写整数", event[2])

    def test_alignment_worker_forwards_actual_resources_and_queues_completion(self):
        summary = {"passed": True}
        cancel = threading.Event()
        with patch("moonalign.engine.run_alignment", return_value=summary) as run:
            app = _ResourceApp()
            MoonAlignApp._run_worker(app, ["a.tif"], "a.tif", "output", 10, 2, cancel)
            self.assertEqual(run.call_args.kwargs["workers"], 10)
            self.assertEqual(run.call_args.kwargs["compute_threads"], 2)
            self.assertEqual(run.call_args.kwargs["memory_policy"], "conservative")
            self.assertIs(run.call_args.kwargs["cancel_event"], cancel)
            run.call_args.kwargs["progress"]({"event": "message"})
            self.assertEqual(app.events.get_nowait(), ("worker_finished", summary))
            self.assertEqual(app.events.get_nowait(), ("engine", {"event": "message"}))

    def test_alignment_worker_forwards_expanded_policy(self):
        with patch("moonalign.engine.run_alignment", return_value={"passed": True}) as run:
            MoonAlignApp._run_worker(_ResourceApp(), ["a.tif"], "a.tif", "output", 5, 2,
                                    threading.Event(), "expanded")
            self.assertEqual(run.call_args.kwargs["memory_policy"], "expanded")

    def test_switching_preset_does_not_clear_checked_advanced_preference(self):
        app = _ResourceApp(mode="均衡（推荐）")
        app.expanded_memory_var.set(True)
        MoonAlignApp._update_performance_controls(app)
        self.assertTrue(app.expanded_memory_var.get())
        self.assertEqual(app.memory_checkbox["state"], "disabled")
        self.assertEqual(_effective_memory_policy("balanced", app.expanded_memory_var.get()), "conservative")

    def test_stale_resource_result_cannot_override_a_new_mode_selection(self):
        app = _ResourceApp()
        app._closed = False
        app._performance_generation = 2
        applied = []
        app._apply_performance = applied.append
        app.after = lambda *_args: None
        app._drain_events = lambda: None
        app.events.put(("performance", 1, self.profile(workers=20)))
        current = self.profile(workers=6)
        app.events.put(("performance", 2, current))
        MoonAlignApp._drain_events(app)
        self.assertEqual(applied, [current])

    def test_late_frame_during_cancel_does_not_restore_eta(self):
        app = _FakeApp()
        app._cancel_event = threading.Event()
        app._cancel_event.set()
        app.runtime_var.set("已请求停止，剩余时间不再估算。")
        app.progress.configure(maximum=10)
        app._file_results = {}
        MoonAlignApp._engine_event(app, {"event": "frame", "stage": "all", "done": 1, "total": 10,
            "filename": "a.tif", "status": "success", "throughput_fps": 5, "eta_seconds": 2})
        self.assertEqual(app.runtime_var.get(), "已请求停止，剩余时间不再估算。")
        self.assertEqual(app.counts_var.get(), "成功 1    失败 0")


if __name__ == "__main__":
    unittest.main()
