# pylint: disable=unused-argument,no-member
from __future__ import annotations

import glob
import logging
import os.path

import pandas as pd
import panel as pn
import xarray as xr

from . import utils
from . import visuals


logger = logging.getLogger(__name__)

DATA_DIR = "./data/"
DATA_GLOB = DATA_DIR + os.path.sep + "*"
MAXIMUM_PLACEHOLDER_TIMESTAMP = pd.to_datetime("1900-01-01")

# CSS Styles
ERROR = {"border": "4px solid red"}
INFO = {"border": "2px solid blue"}


# Help functions that log messages on stdout AND render them on the browser
def info(msg: str) -> pn.Column:
    logger.info(msg)
    return pn.Column(pn.pane.Markdown(msg, style=INFO))


def error(msg: str) -> pn.Column:
    logger.error(msg)
    return pn.Column(pn.pane.Markdown(msg, style=ERROR))


def exception(msg: str) -> pn.Column:
    logger.exception(msg)
    return pn.Column(pn.pane.Markdown(msg, style=ERROR))


class UserInterface:
    """
    This UI is supposed to be used with a Bootstrap-like template supporting
    a "main" and a "sidebar":

    - `sidebar` will contain the widgets that control what will be rendered in the main area.
      E.g. things like which `source_file` to use, which timestamp to render etc.

    - `main` will contain the rendered graphs.

    In a nutshell, an instance of the `UserInteface` class will have two private attributes:

    - `_main`
    - `_sidebar`

    These objects should be of `pn.Column` type. You can append

    This class takes one parameter that needs some explaining though: `timestamp_for_maximum`

    The main piece of information we want to display is the maximum elevation of the sea level.  We
    also want to be able to display the elevation at each timestep. The "problem" is that we also
    want to be avoid having two different graphs. Ideally we want to display the elevation in
    a single graph, regardless if it is the maximum elevation or the elevation at a specific
    timestep.

    In order to achieve this we "inject" the maximum values in the `xr.Dataset` object at the
    timestamp specified by `timestamp_for_maximum`. The default value of `timestamp_for_maximum` is
    `1900-01-01` which we assume that is a safe enough value - i.e. the source files we are going to
    display will not have this value. If that is not the case, then do change it since it will

    """

    def __init__(
        self,
        timestamp_for_maximum: pd.Timestamp = pd.to_datetime("1900-01-01"),
        display_stations: bool = False,
    ) -> None:
        self._timestamp_for_maximum = timestamp_for_maximum
        self._display_stations = display_stations

        # Initialize data variables
        self._dataset: xr.Dataset = xr.Dataset()
        self._variables: list[str] = []

        ## Define widgets
        self.dataset_file = pn.widgets.Select(
            name="Dataset file", options=sorted(filter(utils.can_be_opened_by_xarray, glob.glob(DATA_GLOB)))
        )
        # variables
        self.longitude_var = pn.widgets.Select(name="Longitude")
        self.latitude_var = pn.widgets.Select(name="Latitude")
        self.elevation_var = pn.widgets.Select(name="Elevation")
        self.simplices_var = pn.widgets.Select(name="Simplices")
        self.time_var = pn.widgets.Select(name="Time")
        # display options
        self.timestamp = pn.widgets.Select(name="Timestamp")
        self.relative_colorbox = pn.widgets.Checkbox(name="Relative colorbox")
        self.show_grid = pn.widgets.Checkbox(name="Show Wireframe")
        # stations
        self.stations_file = pn.widgets.Select(name="Stations file")
        self.stations = pn.widgets.CrossSelector(name="Stations")
        # render button
        self.render_button = pn.widgets.Button(name="Render", button_type="primary")

        self._define_callbacks()
        self._populate_widgets()

        self._main = (
            pn.Column()
        )  # info("## Welcome to Thalassa\n\n####Please select a source file and click on 'Render'."))
        self._sidebar = pn.Column(
            pn.Accordion(("Input Files", pn.WidgetBox(self.dataset_file)), active=[0]),
            pn.Accordion(
                (
                    "Variables",
                    pn.WidgetBox(
                        self.longitude_var,
                        self.latitude_var,
                        self.elevation_var,
                        self.simplices_var,
                        self.time_var,
                    ),
                )
            ),
            pn.Accordion(
                ("Display Options", pn.WidgetBox(self.timestamp, self.relative_colorbox, self.show_grid)),
                active=[0],
            ),
            pn.Accordion(("Stations", pn.WidgetBox(self.stations_file, self.stations))),
            self.render_button,
        )

    def _populate_widgets(self) -> None:
        self.dataset_file.param.trigger("value")

    def _define_callbacks(self) -> None:
        self.dataset_file.param.watch(fn=self._update_dataset_file, parameter_names="value")
        # Variable callbacks
        self.dataset_file.param.watch(
            fn=lambda event: self._set_variable(event, self.longitude_var, 1, "SCHISM_hgrid_node_x"),
            parameter_names="value",
        )
        self.dataset_file.param.watch(
            fn=lambda event: self._set_variable(event, self.latitude_var, 2, "SCHISM_hgrid_node_y"),
            parameter_names="value",
        )
        self.dataset_file.param.watch(
            fn=lambda event: self._set_variable(event, self.elevation_var, 0, "elev"),
            parameter_names="value",
        )
        self.dataset_file.param.watch(
            fn=lambda event: self._set_variable(event, self.simplices_var, 3, "SCHISM_hgrid_face_nodes"),
            parameter_names="value",
        )
        self.dataset_file.param.watch(
            fn=lambda event: self._set_variable(event, self.time_var, 4, "time"),
            parameter_names="value",
        )
        # Display options callbacks
        self.dataset_file.param.watch(fn=self._update_timestamp, parameter_names="value")
        # Station callbacks
        # Render button
        self.render_button.on_click(self._update_main)

    @property
    def sidebar(self) -> pn.Column:
        return self._sidebar

    @property
    def main(self) -> pn.Column:
        return self._main

    # Define callbacks
    def _update_dataset_file(self, event: pn.Event) -> None:
        logger.debug("Updating dataset file: %s", self.dataset_file.value)
        self._dataset = utils.open_dataset(self.dataset_file.value, load=False)
        self._variables = list(self._dataset.variables.keys())  # type: ignore[arg-type]

    def _set_variable(self, event: pn.Event, widget: pn.Widget, index: int, schism_name: str) -> None:
        logger.debug("Updating %s", widget.name)
        if schism_name in self._variables:
            value = schism_name
        else:
            try:
                value = self._variables[index]
            except IndexError:
                logger.error("Not enough variables: %d, %s", index, self._variables)
                raise
        widget.param.set_param(options=self._variables, value=value)

    def _update_timestamp(self, event: pn.Event) -> None:
        dataset_timestamps = self._dataset[self.time_var.value].to_pandas().dt.to_pydatetime()
        dataset_options = ["MAXIMUM"] + [v.strftime("%Y-%m-%d %H-%M-%S") for v in dataset_timestamps]
        self.timestamp.param.set_param(options=dataset_options, value="MAXIMUM")

    def _update_main(self, event: pn.Event) -> None:
        logger.info("trimesh")
        self._dataset = utils.open_dataset(self.dataset_file.value, load=True)
        # if self._timestamp_for_maximum in self._dataset[self.time_var.value]:
        # self._main.objects = error("## AAA")
        # return
        utils.inject_maximum_at_timestamp(
            dataset=self._dataset,
            time_var=self.time_var.value,
            timestamp=self._timestamp_for_maximum,
        )
        logger.info("Injected maximum values into elevation data at: %s", self._timestamp_for_maximum)

        trimesh = visuals.get_trimesh(
            self._dataset,
            self.longitude_var.value,
            self.latitude_var.value,
            self.elevation_var.value,
            self.simplices_var.value,
            self.time_var.value,
            timestamp=self.timestamp.value,
        )
        logger.info("created trimesh")
        dmap = visuals.get_elevation_dmap(trimesh, show_grid=self.show_grid.value)
        self._main.objects = []
        logger.info("updated column")
