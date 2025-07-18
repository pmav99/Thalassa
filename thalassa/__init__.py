from __future__ import annotations

__doc__ = """\
Thalassa is a library for visualizing unstructured mesh data with a focus on large scale sea level data.
"""

import importlib.metadata

from .api import open_dataset
from .normalization import normalize
from .plotting import plot
from .plotting import plot_mesh
from .plotting import plot_nodes
from .plotting import plot_ts
from .utils import crop


__version__ = importlib.metadata.version("thalassa")

__all__: list[str] = [
    "__version__",
    "crop",
    "normalize",
    "open_dataset",
    "plot",
    "plot_nodes",
    "plot_mesh",
    "plot_ts",
]
