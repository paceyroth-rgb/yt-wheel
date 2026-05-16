import os
import sys
import traceback
from pathlib import Path

import uvicorn


def main():
    project_root = Path(__file__).resolve().parents[1]

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    port = int(os.environ.get("PORT", "8000"))

    print(f"Starting backend with Python {sys.version}", flush=True)
    print(f"Working directory: {os.getcwd()}", flush=True)
    print(f"Project root: {project_root}", flush=True)
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
