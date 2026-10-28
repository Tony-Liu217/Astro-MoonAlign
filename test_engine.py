"""Core checks. Real-camera integration checks are opt-in through environment.

Default: python -m unittest test_engine
Optional: set MOONALIGN_TEST_INPUT, MOONALIGN_TEST_OUTPUT, and optionally
MOONALIGN_TEST_REFERENCE to run a 10-frame real-data/cancellation/resume check.
The integration output must be a NEW directory, never the original image folder.
"""
from pathlib import Path
import json
import math
import os
import tempfile
import threading
import unittest

import numpy as np
import cv2
from PIL import Image

from moonalign import engine


class CoreTests(unittest.TestCase):
    def setUp(self):
        # Use an explicit writable working directory: some Windows app-container
        # temporary roots permit creation but deny the atomic rename being tested.
        base = Path(os.environ.get('MOONALIGN_TEST_WORKSPACE', str(Path.cwd() / '.test_tmp'))).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='moonalign_core_test_', dir=base))

    def test_rigid_fit_known_rotation_has_no_scale_or_shear(self):
        rng = np.random.default_rng(91)
        source = rng.uniform(0, 1800, (200, 2))
        theta = math.radians(-8.63)
        rotation = np.array([[math.cos(theta), -math.sin(theta)],
                             [math.sin(theta), math.cos(theta)]])
        target = source @ rotation.T + [145.125, -122.375]
        matrix = engine.rigid(source, target)
        np.testing.assert_allclose(engine.transform(source, matrix), target, atol=1e-9)
        np.testing.assert_allclose(matrix[:, :2].T @ matrix[:, :2], np.eye(2), atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(matrix[:, :2]), 1, places=12)

    def test_uint16_rgb_tiff_roundtrip_without_added_icc(self):
        values = np.array([0, 1, 255, 256, 257, 32768, 65534, 65535], np.uint16)
        rgb = np.resize(values, (31, 43, 3))
        path = self.root / '原名.tiff'
        engine.write_tiff(path, rgb, b'')
        report = engine.verify_written(path, rgb, b'')
        self.assertEqual(report['bits'], [16, 16, 16])
        self.assertEqual(report['icc_bytes'], 0)
        self.assertEqual(engine.metadata(path.read_bytes())['compression'], 1)

    def test_icc_is_preserved_exactly(self):
        rgb = np.zeros((17, 19, 3), np.uint16)
        profile = b'opaque-source-profile-do-not-reassign'
        path = self.root / 'profile.tif'
        engine.write_tiff(path, rgb, profile)
        engine.verify_written(path, rgb, profile)
        self.assertEqual(engine.metadata(path.read_bytes())['icc'], profile)

    def test_inspection_supports_both_extensions_and_rejects_mixed_size(self):
        a, b = self.root / 'same.tif', self.root / 'same.tiff'
        engine.write_tiff(a, np.zeros((800, 800, 3), np.uint16), b'')
        engine.write_tiff(b, np.zeros((900, 800, 3), np.uint16), b'')
        result = engine.inspect_files([a, b])
        self.assertEqual(result['valid_count'], 2)
        self.assertFalse(result['uniform_dimensions'])
        self.assertEqual(engine._Job([a, b], a, self.root / 'output', 1, None, None).record_path(a).name,
                         'same.tif.json')
        self.assertEqual(engine._Job([a, b], a, self.root / 'output', 1, None, None).record_path(b).name,
                         'same.tiff.json')

    def test_inspection_rejects_eight_bit_before_decode(self):
        path = self.root / 'eight.tif'
        Image.fromarray(np.zeros((800, 800, 3), np.uint8)).save(path)
        result = engine.inspect_files([path])
        self.assertEqual(result['valid_count'], 0)
        self.assertEqual(len(result['invalid_files']), 1)

    def test_output_must_not_contain_sources(self):
        path = self.root / 'source.tif'
        engine.write_tiff(path, np.zeros((800, 800, 3), np.uint16), b'')
        with self.assertRaises(ValueError):
            engine.run_alignment([path], path, self.root)

    def test_cancel_before_start_writes_no_output(self):
        path = self.root / 'source.tif'
        engine.write_tiff(path, np.zeros((800, 800, 3), np.uint16), b'')
        output = self.root / 'cancelled_output'
        cancel = threading.Event()
        cancel.set()
        events = []
        result = engine.run_alignment([path], path, output, progress=events.append, cancel_event=cancel)
        self.assertTrue(result['cancelled'])
        self.assertFalse(output.exists())
        self.assertEqual(events[-1]['event'], 'done')

    def synthetic_reference(self):
        rng = np.random.default_rng(68)
        texture = cv2.GaussianBlur(rng.uniform(70, 230, (1000, 1000)).astype(np.float32), (0, 0), .8)
        y, x = np.indices((1000, 1000))
        texture[(x - 500)**2 + (y - 500)**2 > 430**2] = 0
        rgb = np.stack((texture * 211, texture * 257, texture * 199), axis=2).astype(np.uint16)
        path = self.root / 'synthetic.tif'
        engine.write_tiff(path, rgb, b'')
        return path

    def test_user_created_empty_output_is_initialized_and_audited(self):
        source = self.synthetic_reference()
        output = self.root / 'user_created_empty_folder'
        output.mkdir()
        result = engine.run_alignment([source], source, output, workers=1)
        self.assertTrue(result['passed'], result)
        self.assertTrue((output / 'job_config.json').is_file())
        self.assertTrue((output / 'frames' / source.name).is_file())

    def test_nonempty_nonjob_output_is_not_touched(self):
        source = self.synthetic_reference()
        output = self.root / 'unrelated_data'
        output.mkdir()
        marker = output / 'keep.txt'
        marker.write_text('unchanged', encoding='utf-8')
        with self.assertRaises(ValueError):
            engine.run_alignment([source], source, output)
        self.assertEqual({p.name for p in output.iterdir()}, {'keep.txt'})
        self.assertEqual(marker.read_text(encoding='utf-8'), 'unchanged')

    def test_exclusive_output_lock(self):
        path = self.root / 'job.lock'
        with engine._JobLock(path):
            with self.assertRaises(RuntimeError):
                with engine._JobLock(path):
                    self.fail('Two writers acquired the same output lock')


@unittest.skipUnless(os.environ.get('MOONALIGN_TEST_INPUT') and os.environ.get('MOONALIGN_TEST_OUTPUT'),
                     'Real-camera data paths were not supplied')
class RealDataIntegration(unittest.TestCase):
    def test_real_ten_frames_and_resume(self):
        source = Path(os.environ['MOONALIGN_TEST_INPUT'])
        output = Path(os.environ['MOONALIGN_TEST_OUTPUT'])
        self.assertFalse(output.exists(), 'Integration output must be a NEW directory')
        all_files = sorted(p for p in source.iterdir() if p.suffix.lower() in ('.tif', '.tiff'))
        ids = np.linspace(0, len(all_files) - 1, min(10, len(all_files))).round().astype(int)
        files = [all_files[i] for i in ids]
        reference = Path(os.environ.get('MOONALIGN_TEST_REFERENCE', str(files[len(files)//2])))
        before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in [*files, reference]}
        cancellation = threading.Event()
        def cancel_after_first(event):
            if event['event'] == 'frame':
                cancellation.set()
        partial = engine.run_alignment(files, reference, output, workers=3,
                    progress=cancel_after_first, cancel_event=cancellation)
        self.assertTrue(partial['cancelled'])
        self.assertGreater(partial['success'], 0)
        self.assertLess(partial['success'], len(files))
        events = []
        first = engine.run_alignment(files, reference, output, workers=3, progress=events.append)
        self.assertTrue(first['passed'], json.dumps(first, ensure_ascii=False))
        self.assertEqual(first['success'], len(files))
        names = {p.name for p in (output / 'frames').iterdir()}
        self.assertEqual(names, {p.name for p in files})
        mtimes = {p.name: p.stat().st_mtime_ns for p in (output / 'frames').iterdir()}
        second = engine.run_alignment(files, reference, output, workers=2)
        self.assertTrue(second['passed'])
        self.assertEqual(second['resumed_frames'], len(files))
        self.assertEqual(mtimes, {p.name: p.stat().st_mtime_ns for p in (output / 'frames').iterdir()})
        # Deliberately corrupt only a test OUTPUT. Checkpoint validation must not
        # silently accept a same-name file whose pixels no longer match its hash.
        repaired_file = output / 'frames' / files[0].name
        data = bytearray(repaired_file.read_bytes())
        data[-1] ^= 1
        repaired_file.write_bytes(data)
        repaired = engine.run_alignment(files, reference, output, workers=2)
        self.assertTrue(repaired['passed'])
        self.assertEqual(repaired['resumed_frames'], len(files) - 1)
        after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in [*files, reference]}
        self.assertEqual(before, after)
        self.assertEqual(events[0]['event'], 'start')
        self.assertEqual(events[-1]['event'], 'done')


if __name__ == '__main__':
    unittest.main()
