import logging.config
import time

import holoviews as hv
import geoviews as gv
import panel as pn
import thalassa
from holoviews.operation.datashader import rasterize  # type: ignore
from ruyaml import YAML

# load configuration
yaml = YAML(typ="safe", pure=True)

with open("config.yml", "rb") as fd:
    config = yaml.load(fd.read())

# configure logging
logging.config.dictConfig(config["logging"])

logger = logging.getLogger("thalassa")

tiles = hv.Tiles("http://c.tile.openstreetmap.org/{Z}/{X}/{Y}.png")
logger.debug("Start")
# tiles = gv.WMTS("http://c.tile.openstreetmap.org/{Z}/{X}/{Y}.png")
logger.debug("Created tiles")

ds = thalassa.open_dataset("data/dataset.nc")
logger.debug("opened dataset")
qq = thalassa.coords_to_web_mercator(ds, "SCHISM_hgrid_node_x", "SCHISM_hgrid_node_y")
logger.debug("reprojected")

trimesh = thalassa.get_trimesh(
    qq, "SCHISM_hgrid_node_x", "SCHISM_hgrid_node_y", "elev", "SCHISM_hgrid_face_nodes", "time"
)
logger.debug("trimesh")

elevation = rasterize(trimesh, aggregator="mean").opts(
    width=600,
    height=400,
    title="Max Elevation",
    colorbar=True,
    clabel="meters",
    show_legend=True,
)
logger.debug("rasterize")

layout = (tiles * elevation)
logger.debug("layout")
pn.Row(layout).servable()
