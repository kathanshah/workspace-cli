"""`gpy`: Python with gspread, pandas and the Google libraries; `import gworkspace` is signed in."""
import os
import subprocess
import sys


def main() -> None:
    # UTF-8 mode: on Windows, print() of ₹ or a Hindi name into a pipe would otherwise crash.
    env = {**os.environ, "PYTHONUTF8": "1"}
    sys.exit(subprocess.call([sys.executable, *sys.argv[1:]], env=env))
