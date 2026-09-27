"""Root conftest — ensures the gltest-direct SDK genlayer is used, not the pip version."""
import sys
from pathlib import Path

# These must be set before any gltest module imports genlayer from pip
_SDK_PATHS = [
    Path.home() / ".cache" / "gltest-direct" / "extracted" / "v0.3.0-rc7" / "py-lib-genlayer-std" / "11rhn002yfajawsz7fai6mykznbxkxs6l91iskj5cm82c92qhy3v",
    Path.home() / ".cache" / "gltest-direct" / "extracted" / "v0.3.0-rc7" / "py-genlayer" / "1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6",
]


def _ensure_sdk_genlayer():
    """Insert SDK paths at front of sys.path and clear any pip-genlayer cache."""
    for p in _SDK_PATHS:
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)

    # If the pip genlayer got loaded first (by gltest imports), evict it so
    # the next "import genlayer" picks up the SDK version.
    for key in list(sys.modules):
        if key == "genlayer" or key.startswith("genlayer."):
            if "site-packages" in sys.modules[key].__file__:
                del sys.modules[key]


# Run before pytest collects tests (module-level code in conftest runs early)
_ensure_sdk_genlayer()
