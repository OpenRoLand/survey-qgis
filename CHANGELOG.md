# Changelog

## [Unreleased]

### Fixed

- Make the nested `survey_qgis` package importable when the plugin is
  installed as `siscadro_survey` (add the plugin directory to
  `sys.path` in the QGIS entry point).
- Declare `qgisMaximumVersion=4.99` in `metadata.txt` so QGIS 3.44+ no
  longer disables the plugin as incompatible.

### Changed

- Snake animation uses a canvas rubber-band overlay instead of a project
  memory layer (no legend entry; follows the canvas temporal range).
- Visible snake segments use a blue→red colormap relative to the current
  time window (oldest blue, newest red), remapped on each temporal step.
- Snake updates listen to the QGIS temporal controller so the built-in
  temporal toolbar drives the overlay as well as the dock controls.
- Connecting path lines are an on-demand memory layer created from the
  Time tab **Generate path lines layer** button, with a cool-to-warm
  color scale for movement direction.

### Added

- New QGIS plugin that loads a siscadro-survey GeoPackage as a managed,
  time-filterable survey observations layer.
- Precomputed survey intervals with a configurable gap threshold and
  optional per-source-file grouping.
- Dock panel pages for source selection, interval browsing with date
  filters, and temporal sliding-window animation.
- Red-line snake overlay that follows consecutive observations during
  temporal autoadvance, colored blue→red within the current window.
- On-demand path-lines memory layer for all connecting segments in the
  selected intervals.
- Time-tab switch to enable or disable sliding-window filtering (when
  off, all interval-selected points remain visible).
- Min/Max tool buttons on the Intervals date filter to jump start/end
  to the database earliest/latest coverage.
- Point labels use description when present, otherwise the point name.
- Docker-based Qt5 and Qt6 test environments (`make test-qt5`,
  `make test-qt6`); no local virtualenv required.
