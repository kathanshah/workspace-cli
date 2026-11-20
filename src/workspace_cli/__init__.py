"""gsuite: Google Sheets and Docs from the terminal, for people and AI agents."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("workspace-cli")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0+source"

REPO = "kathanshah/workspace-cli"
# Installers are attached to every release; "latest" only moves once a release is fully published.
INSTALL_SH = f"https://github.com/{REPO}/releases/latest/download/install.sh"
INSTALL_PS1 = f"https://github.com/{REPO}/releases/latest/download/install.ps1"
