"""dsoxlab — plateforme de labs Linux pilotée par dsoxlab."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Source unique de vérité : la version déclarée dans pyproject.toml,
    # lue depuis les métadonnées du paquet installé. Évite toute dérive
    # entre __version__ et pyproject (bug vécu : CLI figée en 0.1.0).
    __version__ = version("dsoxlab")
except PackageNotFoundError:  # exécution depuis les sources sans installation
    __version__ = "0.0.0+unknown"
