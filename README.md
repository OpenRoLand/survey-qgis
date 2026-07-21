# Siscadro Survey Time Filter (QGIS plugin)

QGIS plugin that loads a siscadro-survey GeoPackage as a managed,
time-filterable survey observations layer. It precomputes survey intervals,
filters by date range, animates a sliding time window via the QGIS Temporal
Controller, and draws a temporary "snake" line between consecutive
observations.

This is private, unpublished code. Do not upload it to a public package
index.

## Requirements

- Docker (all testing and development happens in containers)
- A siscadro-survey GeoPackage (schema version 2)
- Editable sibling libraries under `D:\prog\__py_libs__` (mounted into
  containers as `/libs`):
  - `siscadro-survey`
  - optionally `siscadro-cube`, `siscadro-rw5`, `siscadro-jxl`

There is **no local virtualenv** in this repository.

## Features

- Managed regular `QgsVectorLayer` over a materialized
  `survey_observations` feature table (EPSG:3844)
- Observation-level intervals with configurable gap threshold (default
  30 minutes) and optional per-source-file grouping
- Dock panel with Source, Intervals, and Time pages
- Multi-layer control: when several managed layers exist, choose which
  one the panel drives
- Sliding time window via native QGIS temporal properties
- Legend-hidden snake line layer for autoadvance animation

## Docker tests

```text
make test          # Qt5 (QGIS 3 LTR) and Qt6 (QGIS 4)
make test-qt5
make test-qt6
make shell         # interactive bash in the Qt5 container
```

Images used:

- Qt5: `qgis/qgis:ltr-noble` (QGIS 3.x on Ubuntu Noble)
- Qt6: `qgis/qgis:stable-questing` (QGIS 4.x / Qt6 on Ubuntu Questing)

The compose file mounts this repo at `/plugin` and the sibling
`__py_libs__` directory at `/libs`. The entrypoint installs
`siscadro-survey` (and available format libraries) editable against the
container's QGIS Python, then runs `xvfb-run -a pytest`.

## Deploy to a host QGIS

```text
make deploy QGIS_PLUGIN_DIR="%APPDATA%/QGIS/QGIS4/profiles/default/python/plugins"
```

Alternatively run
`playground/install-qgis-plugin-run-admin.bat` (as Administrator) to create a
junction named `siscadro_survey` into the QGIS 4 plugins folder.

Restart QGIS and enable **Siscadro Survey Time Filter**.

## Usage

1. Open the plugin dock (Plugins / Siscadro Survey Time Filter).
2. On the Source page, pick a `.gpkg` survey database and click
   **Add survey layer**.
3. On Intervals, filter by start/end date, select intervals to show, and
   optionally recompute with a different gap threshold.
4. On Time, set the sliding window size and use play/step to animate;
   enable the snake overlay for the moving path.

## Package layout

```text
siscadro-survey-qgis/
    __init__.py          # classFactory
    metadata.txt
    survey_qgis/
        plugin.py
        core/            # db, schema, observations, intervals, snake
        layers/          # managed layer, snake layer, registry
        gui/             # dock widget pages
    docker/
    tests/
    docker-compose.yml
```
