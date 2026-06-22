import os
import socket
import uvicorn

from viewer.server import app


def _find_free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


port = _find_free_port(int(os.environ.get("KP_VIEWER_PORT", "8080")))
print(f"KP Artifact Viewer — http://127.0.0.1:{port}")
uvicorn.run(app, host="127.0.0.1", port=port)
