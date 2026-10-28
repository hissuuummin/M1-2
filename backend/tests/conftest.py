import os
import sys

# Ensure backend directory and root are in sys.path
test_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(test_dir)
root_dir = os.path.dirname(backend_dir)

for p in [backend_dir, root_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)
