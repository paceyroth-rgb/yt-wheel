import os
import sys
import traceback

import uvicorn


def main():
    port = int(os.environ.get("PORT", "8000"))

    print(f"Starting backend with Python {sys.version}", flush=True)
    print(f"Working directory: {os.getcwd()}", flush=True)
    print(f"Python path: {sys.path}", flush=True)
    print(f"Using port: {port}", flush=True)

    try:
        import backend.main
    except Exception:
        print("Failed to import backend.main:", flush=True)
        traceback.print_exc()
        raise

    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
