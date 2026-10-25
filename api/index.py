import os
import sys

# Ensure HisaabHoshiyaar directory is on the python search path
base_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.abspath(os.path.join(base_dir, "..", "HisaabHoshiyaar"))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from main import app
