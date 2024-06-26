from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import geoviews
    import holoviews
    import xarray

from . import api
from . import normalization

logger = logging.getLogger(__name__)


def _sanity_check(ds: xarray.Dataset, variable: str) -> None:
    dims = ds[variable].dims
    if "node" not in dims:
        msg = (
            f"Only variables whose dimensions include 'node' can be plotted. "
            f"The dimensions of variable '{variable}' are: {ds[variable].dims}"
        )
        raise ValueError(msg)
    if dims != ("node",):
        msg = (
            f"In order to plot variable '{variable}', the dataset must be filtered in such a way "
            f"that the only dimension of '{variable}' is `node`. Please use `.sel()` or `.isel()` "
            f"to filter the dataset accordingly. Current dimensions are: {ds[variable].dims}"
        )
        raise ValueError(msg)


def plot_nodes(
    ds: xarray.Dataset,
    *,
    title: str = "Nodes",
    x_range: tuple[float, float] | None = None,
    y_range: tuple[float, float] | None = None,
    size: float = 4,
) -> holoviews.Overlay:
    """
    Plot the nodes of the mesh.

    Examples:
        ``` python
        import thalassa

        ds = thalassa.open_dataset("some_netcdf.nc")
        thalassa.plot_nodes(ds)
        ```

    Parameters:
        ds: The dataset whose mesh we want to visualize. It must adhere to the "thalassa schema"
        title: The title of the plot
        x_range: A tuple specifying the range of the longitudes of the plotted area
        y_range: A tuple specifying the range of the latitudes of the plotted area
        size: The size of the points in the plot

    """
    import holoviews as hv

    ds = normalization.normalize(ds)
    tiles = api.get_tiles()
    nodes = api.get_nodes(ds, x_range=x_range, y_range=y_range, hover=True, size=size)
    overlay = hv.Overlay((tiles, nodes)).opts(title=title).collate()
    return overlay


def plot_mesh(
    ds: xarray.Dataset,
    *,
    title: str = "Mesh",
    x_range: tuple[float, float] | None = None,
    y_range: tuple[float, float] | None = None,
) -> geoviews.DynamicMap:
    """
    Plot the mesh of the dataset

    Examples:
        ``` python
        import thalassa

        ds = thalassa.open_dataset("some_netcdf.nc")
        thalassa.plot_mesh(ds)
        ```

    Parameters:
        ds: The dataset whose mesh we want to visualize. It must adhere to the "thalassa schema"
        title: The title of the plot.
        x_range: A tuple specifying the range of the longitudes of the plotted area
        y_range: A tuple specifying the range of the latitudes of the plotted area

    """
    import holoviews as hv

    ds = normalization.normalize(ds)
    tiles = api.get_tiles()
    mesh = api.get_wireframe(ds, x_range=x_range, y_range=y_range, hover=True)
    overlay = hv.Overlay((tiles, mesh)).opts(title=title).collate()
    return overlay


def plot(
    ds: xarray.Dataset,
    variable: str,
    *,
    title: str = "",
    cmap: str = "plasma",
    colorbar: bool = True,
    clabel: str = "",
    clim_min: float | None = None,
    clim_max: float | None = None,
    x_range: tuple[float, float] | None = None,
    y_range: tuple[float, float] | None = None,
    show_mesh: bool = False,
    show_nodes: bool = False,
    node_size: float = 3,
) -> geoviews.DynamicMap:
    """
    Return the plot of the specified `variable`.

    Examples:
        ``` python
        import thalassa

        ds = thalassa.open_dataset("some_netcdf.nc")
        thalassa.plot(ds, variable="zeta_max")
        ```

        When we plot time dependent variables we need to filter the data
        in such a way that `time` is no longer a dimension.
        For example to plot the map of the first timestamp of variable `zeta`:

        ``` python
        import thalassa

        ds = thalassa.open_dataset("some_netcdf.nc")
        thalassa.plot(ds.isel(time=0), variable="zeta")
        ```

        Often, it is quite useful to limit the range of the colorbar:

        ``` python
        import thalassa

        ds = thalassa.open_dataset("some_netcdf.nc")
        thalassa.plot(ds, variable="zeta", clim_min=1, clim_max=3, clabel="meter")
        ```

    Parameters:
        ds: The dataset which will get visualized. It must adhere to the "thalassa schema".
        variable: The dataset's variable which we want to visualize.
        title: The title of the plot. Defaults to `variable`.
        cmap: The colormap to use.
        colorbar: Boolean flag indicating whether the plot should have an integrated colorbar.
        clabel: A caption for the colorbar. Useful for indicating e.g. units
        clim_min: The lower limit for the colorbar.
        clim_max: The upper limit for the colorbar.
        x_range: A tuple indicating the minimum and maximum longitude to be displayed.
        y_range: A tuple indicating the minimum and maximum latitude to be displayed.
        show_mesh: A boolean flag indicating whether the mesh should be overlaid on top of the data.
            Enabling this makes rendering slower.
        show_nodes: A boolean flag indicating whether the nodes should be overlaid on top of the data.
            Enabling this makes rendering slower.
        node_size: A float value indicating the size of the nodes. Only used if `show_nodes=True`.

    """
    import holoviews as hv

    ds = normalization.normalize(ds)
    _sanity_check(ds=ds, variable=variable)
    trimesh = api.create_trimesh(ds_or_trimesh=ds, variable=variable)
    raster = api.get_raster(
        ds_or_trimesh=trimesh,
        variable=variable,
        x_range=x_range,
        y_range=y_range,
        cmap=cmap,
        colorbar=colorbar,
        clim_min=clim_min,
        clim_max=clim_max,
        title=title,
        clabel=clabel,
    )
    tiles = api.get_tiles()
    components = [tiles, raster]
    if show_mesh:
        mesh = api.get_wireframe(trimesh, x_range=x_range, y_range=y_range, hover=False)
        components.append(mesh)
    if show_nodes:
        nodes = api.get_nodes(trimesh, x_range=x_range, y_range=y_range, hover=True, size=node_size)
        components.append(nodes)
    overlay = hv.Overlay(components)
    dmap = overlay.collate()
    # Keep a reference of the raster DynamicMap, in order to be able to retrieve it from plot_ts
    dmap._raster = raster
    return dmap


def plot_ts(
    ds: xarray.Dataset,
    variable: str,
    source_plot: geoviews.DynamicMap,
) -> geoviews.DynamicMap:
    """
    Return a plot with the full timeseries of a specific node.

    The node that will be visualized is selected by clicking on `source_plot`.

    Examples:
        ``` python
        import thalassa

        ds = thalassa.open_dataset("some_netcdf.nc")
        main_plot = thalassa.plot(ds, variable="zeta_max")
        ts_plot = thalassa.plot_ts(ds, variable="zeta", source_plot=main_plot)

        (main_plot + ts_plot.opts(width=600)).cols(1)
        ```

    Parameters:
        ds: The dataset which will get visualized. It must adhere to the "thalassa schema"
        variable: The dataset's variable which we want to visualize.
        source_plot: The plot instance which be used to select the coordinates of the node.
            Normally, you get this instance by calling `plot()`.
    """
    ds = normalization.normalize(ds)
    ts = api.get_tap_timeseries(ds, variable, source_plot._raster)
    return ts
