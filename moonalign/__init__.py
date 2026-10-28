"""MoonAlign: lunar image pre-registration for AutoStakkert."""

__version__ = "1.1.1"


def startup_failure(details: str) -> int:
    """Report even an import failure when the Windows build has no console."""
    import ctypes
    from datetime import datetime
    import os
    from pathlib import Path
    import tempfile

    path = None
    try:
        base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
        folder = base / "MoonAlign" / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "error.log"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"\n{datetime.now().isoformat(timespec='seconds')}\n{details}\n")
    except OSError:
        pass
    message = "MoonAlign 无法启动。"
    if path:
        message += f"\n\n错误详情已保存到：\n{path}"
    try:
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(None, message, "MoonAlign", 0x10)
        else:
            from tkinter import messagebox
            messagebox.showerror("MoonAlign", message)
    except Exception:
        pass
    return 1

