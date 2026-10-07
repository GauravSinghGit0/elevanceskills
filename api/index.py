import os
import sys

# Ensure root project directory is added to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookmyseat.wsgi import app
