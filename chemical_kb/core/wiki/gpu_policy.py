"""Local GPU permission shared by Wiki API and inference worker."""
import os


def local_gpu_allowed():
    # The user authorizes local inference by default; explicit opt-out remains available.
    return os.environ.get("CHEM_KB_WIKI_ALLOW_LOCAL_GPU", "1").strip().lower() in {"1", "true", "yes", "on"}
