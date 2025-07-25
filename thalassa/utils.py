from __future__ import annotations

import logging
import sys
import time
import typing as T

import decorator


if T.TYPE_CHECKING:  # pragma: no cover
    import geopandas
    import geoviews
    import holoviews
    import numpy
    import numpy.typing as npt
    import pandas
    import shapely
    import xarray


logger = logging.getLogger(__name__)


def resolve_bbox(
    bbox: shapely.Polygon | tuple[float, float, float, float] | None = None,
) -> shapely.Polygon:
    import shapely

    if bbox is None:
        bbox = shapely.box(-180, -90, 180, 90)
    elif isinstance(bbox, tuple):
        bbox = shapely.box(*bbox)
    else:
        pass
    return bbox


def crop(
    ds: xarray.Dataset,
    bbox: shapely.Polygon,
) -> xarray.Dataset:
    """
    Crop the dataset using the provided `bbox`.

    Examples:
        ``` python
        import thalassa
        import shapely

        ds = thalassa.open_dataset("some_netcdf.nc")
        bbox = shapely.box(0, 0, 1, 1)
        ds = thalassa.crop(ds, bbox)
        ```

    Parameters:
        ds: The dataset we want to crop.
        bbox: A Shapely polygon whose boundary will be used to crop `ds`.
    """
    import numpy as np
    import numpy_indexed as npi

    bbox = resolve_bbox(bbox)
    indices_of_nodes_in_bbox = np.where(
        True
        & (ds.lat >= bbox.bounds[1])
        & (ds.lat <= bbox.bounds[3])
        & (ds.lon >= bbox.bounds[0])
        & (ds.lon <= bbox.bounds[2]),
    )[0]
    indices_of_triface_nodes_in_bbox = np.where(
        ds.triface_nodes.isin(indices_of_nodes_in_bbox).all(axis=1),
    )[0]
    ds = ds.isel(node=indices_of_nodes_in_bbox, triface=indices_of_triface_nodes_in_bbox)
    remapped_nodes = np.arange(len(indices_of_nodes_in_bbox))
    remapped_triface_nodes = np.c_[
        npi.remap(ds.triface_nodes[:, 0], indices_of_nodes_in_bbox, remapped_nodes),
        npi.remap(ds.triface_nodes[:, 1], indices_of_nodes_in_bbox, remapped_nodes),
        npi.remap(ds.triface_nodes[:, 2], indices_of_nodes_in_bbox, remapped_nodes),
    ]
    ds["triface_nodes"] = (("triface", "three"), remapped_triface_nodes)
    return ds


def generate_thalassa_ds(
    nodes: npt.ArrayLike,
    triface_nodes: npt.NDArray[numpy.int_],
    lons: npt.NDArray[numpy.float64] | None = None,
    lats: npt.NDArray[numpy.float64] | None = None,
    time_range: pandas.DatetimeIndex | None = None,
    **kwargs: dict[str, tuple[tuple[str], npt.NDArray[numpy.float64]]],
) -> xarray.Dataset:
    """Return a "thalassa" dataset"""
    import xarray as xr

    # Coordinates
    coords = dict(
        node=nodes,
        triface=range(len(triface_nodes)),
    )
    if time_range is not None:
        coords["time"] = (("time"), time_range)  # type:ignore[assignment]
    # Data Variables
    data_vars: dict[str, T.Any] = {
        "triface_nodes": (("triface", "three"), triface_nodes),
        **kwargs,
    }
    if lons:
        data_vars["lon"] = (("node"), lons)
    if lats:
        data_vars["lat"] = (("node"), lats)
    ds = xr.Dataset(
        coords=coords,
        data_vars=data_vars,
    )
    return ds


_VISUALIZABLE_DIMS = {
    ("node",),
    ("time", "node"),
    ("time", "node", "layer"),
}


def is_variable_visualizable(ds: xarray.Dataset, variable: str) -> bool:
    """
    Return `True` if thalassa can visualize the variable, `False` otherwise.
    """
    if variable in {"lon", "lat"}:
        return False
    return ds[variable].dims in _VISUALIZABLE_DIMS


def filter_visualizable_data_vars(ds: xarray.Dataset, variables: T.Iterable[str]) -> list[str]:
    visualizable = []
    for var in variables:
        if is_variable_visualizable(ds=ds, variable=var):
            visualizable.append(var)
    return visualizable


def split_quads(face_nodes: npt.NDArray[numpy.int_]) -> npt.NDArray[numpy.int_]:
    """
    https://gist.github.com/pmav99/5ded91f18ef096b080b2ed45598c7d1c
    """
    import numpy as np
    import numpy.typing as npt

    if face_nodes.shape[-1] != 4:
        return face_nodes

    # We assume that the nans only exist in the last column
    # Therefore the first 3 columns are the existing triangles
    existing_triangles = face_nodes[:, :3]

    # Identify the quads. They are the rows with nan in the last column
    # The nonzero() function is a speed optimization. With this, we only keep
    # the index  values we care about, instead of the whole boolean array
    quad_indexes = np.nonzero(~np.isnan(face_nodes).any(axis=1))
    quads = face_nodes[quad_indexes]

    # Create the new triangles
    quads_first_column = quads[:, 0]
    quads_last_two_columns = quads[:, -2:]
    new_triangles = np.c_[quads_first_column, quads_last_two_columns]

    # Append new triangles to the existing ones
    # Also cast to the proper type for Mypy
    new_face_nodes = T.cast(
        npt.NDArray[np.int_],
        np.r_[existing_triangles, new_triangles].astype(int),
    )
    return new_face_nodes
    # return new_face_nodes.astype(int)


def get_index_of_nearest_node(ds: xarray.Dataset, lon: float, lat: float) -> int:
    # https://www.unidata.ucar.edu/blogs/developer/en/entry/accessing_netcdf_data_by_coordinates
    # https://github.com/Unidata/python-workshop/blob/fall-2016/notebooks/netcdf-by-coordinates.ipynb
    dist = abs(ds.lon - lon) ** 2 + abs(ds.lat - lat) ** 2
    index_of_nearest_node = int(dist.argmin())
    return index_of_nearest_node


def drop_elements_crossing_idl(
    ds: xarray.Dataset,
    max_lon: float = 10,
) -> xarray.Dataset:
    """
    Drop triface elements crossing the International Date Line (IDL).

    ``max_lon`` is the maximum longitudinal "distance" in degrees for an element.

    What we are actually trying to do in this function is to identify mesh triangles that cross
    the IDL. The truth is that when you have a triplet of nodes you can't really know if the
    triangle they create is the one in `[-180, 180]` or the one that crosses the IDL.
    So here we make one assumption: That we are dealing with a global mesh with a lot of elements.
    Therefore we assume that the elements that cross the IDL are the ones that:
    1. have 2 nodes with different longitudinal sign, e.g. -179 and 179
    2. the absolute of the difference of the longitudes is greater than a user defined threshold
       e.g. `|179 - (-179)| >= threshold`
    The second rule exists to remove false positives close to Greenwich (e.g. 0.1 and -0.1)
    These rules can lead to false positives close to the poles (e.g. latitudes > 89) especially
    if a small value for `max_lon` is used. Nevertheless, the main purpose of this function is
    to visualize data, so some false positives are not the end of the wold.
    """
    import numpy as np

    if max_lon <= 0:
        raise ValueError(f'Maximum longitudinal "distance" must be positive: {max_lon}')
    a, b, c = ds.triface_nodes.data.T
    lon = ds.lon.data
    lon_a = lon[a]
    lon_b = lon[b]
    lon_c = lon[c]
    # `np.asarray(condition).nonzero()` is equivalent to `np.where(condition)`
    # For more info check the help of `np.where()`
    condition = (
        # fmt: off
        ((lon_a * lon_b < 0) & (np.abs(lon_a - lon_b) >= max_lon))
        | ((lon_a * lon_c < 0) & (np.abs(lon_a - lon_c) >= max_lon))
        | ((lon_b * lon_c < 0) & (np.abs(lon_b - lon_c) >= max_lon))
        # fmt: on
    )
    indices_of_triface_nodes_crossing_idl = np.asarray(condition).nonzero()[0]
    ds = ds.drop_isel(triface=indices_of_triface_nodes_crossing_idl)
    return ds


def get_bbox_from_raster(raster: geoviews.DynamicMap) -> holoviews.core.boundingregion.BoundingBox:
    # XXX Even though they seem the same,
    #       raster[()]
    # and
    #       raster.values[0]
    # are not exactly the same. The latter one throws IndexErrors if you run
    # it too soon after the creation of the raster!
    image = raster[()]
    bbox = image.bounds
    return bbox


def get_x_range_from_bbox(bbox: holoviews.core.boundingregion.BoundingBox) -> tuple[float, float]:
    aarect = bbox.aarect()
    x_range = (aarect.left(), aarect.right())
    return x_range


def get_y_range_from_bbox(bbox: holoviews.core.boundingregion.BoundingBox) -> tuple[float, float]:
    aarect = bbox.aarect()
    y_range = (aarect.bottom(), aarect.top())
    return y_range


def is_point_in_the_raster(raster: geoviews.DynamicMap, lon: float, lat: float) -> bool:
    """
    Return ``True`` if the point is inside the mesh of the ``raster``, ``False`` otherwise.

    Do notice that the zoom level and the size of the viewport are taken into account.
    This means that if you change the zoom level of the raster, the return value
    may change.

    For example, let's use the mesh from STOFS and point ``(22, 40)`` which is located in
    the Balkan Peninsula. if we execute  the following snippet on two different
    jupyterlab cells, the return values are going to be ``True`` and ``False`` respectively,

        # low resolution
        stofs_raster.opts(width=200, height=200)
        assert is_point_in_the_raster(stofs_raster, 22, 40)
        # vs
        # higher resolution
        stofs_raster.opts(width=600, height=600)
        assert not is_point_in_the_raster(stofs_raster, 22, 40)

    """
    import numpy as np

    raster_dataset = raster.values()[0].data
    data_var_name = raster.ddims[-1].name
    interpolated = raster_dataset[data_var_name].interp(dict(lon=lon, lat=lat)).data
    return T.cast(bool, ~np.isnan(interpolated))


def generate_mesh_polygon(ds: xarray.Dataset) -> geopandas.GeoDataFrame:
    """Return a ``geopandas.GeoDataFrame`` containing the union of all the polygons"""
    import geopandas as gpd
    import numpy as np
    import shapely

    logger.debug("Starting polygon generation")
    # Get the indexes of the nodes
    triface_nodes = ds.triface_nodes.data
    nodes = ds.node.data
    first_nodes = nodes[triface_nodes[:, 0]]
    second_nodes = nodes[triface_nodes[:, 1]]
    third_nodes = nodes[triface_nodes[:, 2]]
    del triface_nodes
    del nodes

    lons = ds.lon.data
    lats = ds.lat.data
    first_lons = lons[first_nodes]
    second_lons = lons[second_nodes]
    third_lons = lons[third_nodes]
    del lons

    lats = ds.lat.data
    first_lats = lats[first_nodes]
    second_lats = lats[second_nodes]
    third_lats = lats[third_nodes]
    del lats
    del first_nodes
    del second_nodes
    del third_nodes

    # Stack the coords, one polygon per line
    polygons_per_line = np.vstack(
        (
            first_lons,
            first_lats,
            second_lons,
            second_lats,
            third_lons,
            third_lats,
            first_lons,
            first_lats,
        ),
    ).T

    # Re-stack the polygon coords. This time we should have 4 points per line
    polygons_coords = np.stack(
        (
            polygons_per_line[:, :2],
            polygons_per_line[:, 2:4],
            polygons_per_line[:, 4:6],
            polygons_per_line[:, 6:8],
        ),
        axis=1,
    )
    # sanity check
    if polygons_coords.shape[1:] != (4, 2):
        raise ValueError("Something went wrong")
    del polygons_per_line

    polygons = shapely.polygons(polygons_coords)
    polygon = shapely.coverage_union_all(polygons)
    del polygons

    # convert to GeoDataFrame
    gdf = gpd.GeoDataFrame(geometry=[polygon])
    return gdf


@decorator.contextmanager
def timer(
    msg: str = "",
    log_level: int = logging.DEBUG,
    stacklevel: int = 0,
) -> T.Generator[T.Any, T.Any, T.Any]:
    t1 = time.perf_counter()
    yield
    elapsed = time.perf_counter() - t1
    if not stacklevel:
        stacklevel = 5 if sys._getframe(2).f_code.co_filename.endswith("site-packages/decorator.py") else 3
    if msg:
        logger.log(log_level, "%s: %.9fs", msg, elapsed, stacklevel=stacklevel)
    else:
        logger.log(log_level, "%.9fs", elapsed, stacklevel=stacklevel)
