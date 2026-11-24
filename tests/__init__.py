"""Test package setup: on macOS, /usr/bin/git is a shim that looks up the developer directory on every call, which
makes each git command about three times slower. Put the real git first on PATH, once, for the whole test run
(through a folder that holds only a link to it, so the developer tools' own python3 does not shadow ours)."""
import atexit
import os
import shutil
import subprocess
import sys
import tempfile

if sys.platform == "darwin" and shutil.which("git") == "/usr/bin/git":
    try:
        real = subprocess.run(["xcrun", "--find", "git"], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        real = ""
    if real and real != "/usr/bin/git" and os.access(real, os.X_OK):
        _bin = tempfile.mkdtemp(prefix="herd-test-git-")
        atexit.register(shutil.rmtree, _bin, True)
        os.symlink(real, os.path.join(_bin, "git"))
        os.environ["PATH"] = _bin + os.pathsep + os.environ.get("PATH", "")


from scripts import herd  # noqa: E402
from tests import fastgit  # noqa: E402

fastgit.install(herd)
