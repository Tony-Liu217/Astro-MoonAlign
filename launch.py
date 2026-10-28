"""Desktop entry point and an optional, strictly windowless runtime check."""


def self_check(report_path):
    """Exercise the frozen runtime and RGB16 codec without starting Tk."""
    from pathlib import Path
    import json
    import sys
    import tempfile
    import traceback
    report_path = Path(report_path).resolve()
    report = {'passed': False, 'window_created': False}
    try:
        import cv2
        import numpy as np
        import PIL
        import tkinter
        from moonalign import __version__
        from moonalign import gui
        from moonalign.engine import rigid, transform, write_tiff, verify_written

        report['application_version'] = __version__
        report['frozen'] = bool(getattr(sys, 'frozen', False))
        report['versions'] = {'opencv': cv2.__version__, 'numpy': np.__version__,
                              'Pillow': PIL.__version__, 'Tk': tkinter.TkVersion}
        points = np.array([[0., 0.], [17., 2.], [3., 16.], [15., 18.]])
        a = np.deg2rad(3.125)
        expected = np.array([[np.cos(a), -np.sin(a), 2.75],
                             [np.sin(a), np.cos(a), -1.25]])
        estimated = rigid(points, transform(points, expected))
        error = float(np.max(np.abs(estimated - expected)))
        if error > 1e-10:
            raise RuntimeError('Rigid transform numerical check failed')
        rgb = (np.arange(40 * 40 * 3, dtype=np.uint16) * 13).reshape(40, 40, 3)
        rgb[0, 0] = [1, 32769, 65535]
        rgb = cv2.warpAffine(rgb, np.array([[1., 0, 0], [0, 1., 0]]),
                             (40, 40), flags=cv2.INTER_CUBIC)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='MoonAlign_check_', dir=report_path.parent) as folder:
            tiff = Path(folder) / 'rgb16.tif'
            write_tiff(tiff, rgb, b'')
            report['tiff'] = verify_written(tiff, rgb, b'')
        cv2.SIFT_create().detectAndCompute(np.uint8(rgb[:, :, 0] // 256), None)
        report.update(passed=True, rigid_maximum_error=error,
                      gui_imported=gui.MoonAlignApp is not None)
    except Exception:
        report['error'] = traceback.format_exc()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1

def main():
    import sys
    import traceback
    from moonalign import startup_failure

    if len(sys.argv) > 1 and sys.argv[1] == '--self-check':
        return self_check(sys.argv[2]) if len(sys.argv) == 3 else 2
    try:
        from moonalign.gui import main as gui_main
        return gui_main()
    except Exception:
        return startup_failure(traceback.format_exc())


if __name__ == "__main__":
    import sys
    sys.exit(main())

