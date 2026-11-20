"""gsuite: Google Sheets and Docs from the terminal, for people and AI agents."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("workspace-cli")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0+source"

REPO = "kathanshah/workspace-cli"
# Per-OS installer links and behaviour: see platforms/. Installers are attached to every release;
# "latest" only moves once a release is fully published.
