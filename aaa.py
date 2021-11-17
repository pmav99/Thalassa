from __future__ import annotations
import glob
import os

import geoviews as gv
import holoviews as hv
import numpy as np
import pandas as pd
import panel as pn
import xarray as xr
from holoviews import opts as hvopts
from holoviews.operation.datashader import dynspread  # type: ignore
from holoviews.operation.datashader import datashade  # type: ignore
from holoviews.operation.datashader import rasterize  # type: ignore

import thalassa

hv.extension("bokeh")
pn.extension(sizing_mode="stretch_width")

# Set some defaults for the visualization of the graphs
hvopts.defaults(
    hvopts.Image(width=800, height=400, show_title=True, tools=["hover"]),
    hvopts.Layout(toolbar="right"),
)


DATA_GLOB = "data/*"


def load_stations(file: os.PathLike) -> pd.DataFrame:
    df = pd.DataFrame(
        dict(
            lat=[-1, 0, 1, 2, 3],
            lon=[-10, 0, 10, 20, 30],
            time=pd.date_range("2000-01-01", "2000-01-05"),
            name="a,a,a,b,b".split(","),
            station_id=[1, 1, 1, 2, 2],
            metadata=range(5),
        )
    )
    return df


def create_widgets():
    dataset_file = pn.widgets.Select(name="Dataset file", options=sorted(filter(thalassa.utils.can_be_opened_by_xarray, glob.glob(DATA_GLOB))))
    # variables
    longitude_var = pn.widgets.Select(name="Longitude")# value=dataset_vars[1], options=dataset_vars)
    latitude_var = pn.widgets.Select(name="Latitude")# value=dataset_vars[2], options=dataset_vars)
    elevation_var = pn.widgets.Select(name="Elevation")# value=dataset_vars[0], options=dataset_vars)
    simplices_var = pn.widgets.Select(name="Simplices ")# value=dataset_vars[3], options=dataset_vars)
    time_var = pn.widgets.Select(name="Time")# value=dataset_vars[4], options=dataset_vars)
    # Display options
    timestamp = pn.widgets.Select(name='Timestamp')
    relative_colorbox = pn.widgets.Checkbox(name="Relative colorbox")
    show_grid = pn.widgets.Checkbox(name="Show Wireframe")
    # stations
    stations_file = pn.widgets.Select(name="Stations file")
    stations = pn.widgets.CrossSelector(name='Stations')# value=[], options=stations_df.name.unique().tolist())
    # Render
    render_button = pn.widgets.Button(name="Render", button_type="primary")

    return dataset_file, longitude_var, latitude_var, elevation_var, simplices_var, time_var, timestamp, relative_colorbox, show_grid, stations_file, stations, render_button


def set_widgets_options_and_values(
    dataset_vars: list(str),
    longitude_var,
    latitude_var,
    elevation_var,
    simplices_var,
    time_var
) -> None:
    # Set options
    longitude_var.options = dataset_vars
    latitude_var.options = dataset_vars
    elevation_var.options = dataset_vars
    simplices_var.options = dataset_vars
    time_var.options = dataset_vars

    # Set values
    longitude_var.value = "SCHISM_hgrid_node_x" if "SCHISM_hgrid_node_x" in dataset_vars else str(dataset_vars[1])
    latitude_var.value = "SCHISM_hgrid_node_y" if "SCHISM_hgrid_node_y" in dataset_vars else str(dataset_vars[2])
    elevation_var.value = "elev" if "elev" in dataset_vars else str(dataset_vars[0])
    simplices_var.value = "SCHISM_hgrid_face_nodes" if "SCHISM_hgrid_face_nodes" in dataset_vars else str(dataset_vars[3])
    time_var.value = "time" if "time" in dataset_vars else str(dataset_vars[4])


def inject_maximum(dataset: xr.Dataset, time_var: str, timestamp: str = "1900-01-01") -> xr.Dataset:
    """
    Inject the maximum values along the `time_var` dimension at the `timestamp` coordinate
    """
    dataset = xr.concat(
        (
            dataset.max(time_var).expand_dims(dict(time_var=[pd.to_datetime(timestamp)])),
            dataset,
        ),
        dim=time_var,
    )
    return dataset


def get_elevation(
    dataset,
    longitude_var,
    latitude_var,
    simplices_var,
    elevation_var,
    time_var,
    timestamp,
    show_grid,
):
    trimesh = 1


def update_widgets(
    dataset: xr.Dataset,
    dataset_vars: list(str),
    longitude_var,
    latitude_var,
    elevation_var,
    simplices_var,
    time_var,
    timestamp,
) -> None:
    set_widgets_options_and_values(
        dataset_vars=dataset_vars,
        longitude_var=longitude_var,
        latitude_var=latitude_var,
        elevation_var=elevation_var,
        simplices_var=simplices_var,
        time_var=time_var,
    )

    timestamp.options = ["MAXIMUM"] + [v.strftime("%Y-%m-%d %H-%M-%S") for v in dataset[time_var.value].to_pandas().dt.to_pydatetime()]
    timestamp.value = ["MAXIMUM"]


def main():
    dataset_file, longitude_var, latitude_var, elevation_var, simplices_var, \
        time_var, timestamp, relative_colorbox, show_grid, stations_file, \
        stations, render_button = create_widgets()

    dataset = thalassa.open_dataset(dataset_file.value, load=False)
    dataset_vars = list(dataset.variables)

    updated = pn.bind(
        update_widgets,
        dataset=dataset,
        dataset_vars=dataset_vars,
        longitude_var=longitude_var,
        latitude_var=latitude_var,
        elevation_var=elevation_var,
        simplices_var=simplices_var,
        time_var=time_var,
        timestamp=timestamp,
    )

    # layout
    left = pn.Column(
        pn.Accordion(("Input Files", pn.WidgetBox(dataset_file)), active=[0]),
        pn.Accordion(("Variables", pn.WidgetBox(longitude_var, latitude_var, elevation_var, simplices_var, time_var))),
        pn.Accordion(("Display Options", pn.WidgetBox(timestamp, relative_colorbox, show_grid)), active=[0]),
        pn.Accordion(("Stations", pn.WidgetBox(stations_file, stations))),
        render_button,
    )

    msg = f"""
    #### The dataset you chose has less than 5 data variables, therefore cannot be used.
    Please choose an appropriate one."
    """
    if len(dataset_vars) < 4:
        right = pn.Column(
            pn.pane.Alert(msg, alert_type="danger")
        )
    else:
        right = pn.Column()
    return left, right


left, right = main()
pn.template.BootstrapTemplate(
    site="Panel",
    title="Random Number Generator",
    sidebar=[left],
    main=[
        "This example creates a **random number generator**",
        right,
    ],
    # main_max_width="768px",
).servable();

"""
# open datasets
dataset = thalassa.open_dataset(dataset_file.value)
dataset = inject_maximum(dataset)
dataset_vars = list(dataset.variables.keys())

stations_df = load_stations(stations_file.value)

timestamp_options = ["MAXIMUM"] + [v.strftime("%Y-%m-%d %H-%M-%S") for v in dataset[time_var.value].to_pandas().dt.to_pydatetime()]
timestamp = pn.widgets.Select(name='Timestamp', options=timestamp_options)

wb_input_files = pn.WidgetBox(
            dataset_file,
)
wb_variables = pn.WidgetBox(
            longitude_var,
            latitude_var,
            elevation_var,
            simplices_var,
            time_var,
)
wb_display_options = pn.WidgetBox(
            timestamp,
            relative_colorbox,
            show_grid,
)
wb_stations = pn.WidgetBox(
    #"### Stations",
    stations_file,
    stations,
    sizing_mode="stretch_width",
)
render_button = pn.widgets.Button(name='Render', button_type='primary')

def render(event):
    right_column.objects = [thalassa.get_max_elevation(trimesh, show_grid=show_grid.value)]

render_button.on_click(render)

left_column = pn.Column(
    pn.Accordion(
        ("Input Files", wb_input_files),
        ("Variables", wb_variables),
        ("Display Options", wb_display_options),
        ("Stations", wb_stations),
        active=[0, 2],
        sizing_mode="stretch_width",
    ),
    render_button,
)
right_column = pn.Column(
    thalassa.get_max_elevation(trimesh, show_grid=show_grid.value),
)

row = pn.Row(left_column, right_column)

pn.template.BootstrapTemplate(
    site="Panel",
    title="Random Number Generator",
    main=[
        "This example creates a **random number generator** that updates periodically or with the click of a button.\n\nThis demonstrates how to add a **periodic callback** and how to link a button and a toggle to a couple of callbacks.",
        row,
    ],
    # main_max_width="768px",
).servable();
"""
