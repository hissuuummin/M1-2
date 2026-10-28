"""
Investment Mirror - Top-level Launcher
"""
import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")
for p in [backend_dir, root_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
