if __name__ == "__main__":
    import sys
    import traceback
    from . import startup_failure

    try:
        from .gui import main
        result = main()
    except Exception:
        result = startup_failure(traceback.format_exc())
    sys.exit(result)

