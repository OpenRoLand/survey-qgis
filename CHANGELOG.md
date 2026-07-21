# Changelog

## [Unreleased]

### Fixed

- Make the nested `survey_qgis` package importable when the plugin is
  installed as `siscadro_survey` (add the plugin directory to
  `sys.path` in the QGIS entry point).
- Declare `qgisMaximumVersion=4.99` in `metadata.txt` so QGIS 3.44+ no
  longer disables the plugin as incompatible.

### Added

- New QGIS plugin that loads a siscadro-survey GeoPackage as a managed,
  time-filterable survey observations layer.
- Precomputed survey intervals with a configurable gap threshold and
  optional per-source-file grouping.
- Dock panel pages for source selection, interval browsing with date
  filters, and temporal sliding-window animation.
- Temporary (legend-hidden) snake line layer that follows consecutive
  observations during temporal autoadvance.
- Docker-based Qt5 and Qt6 test environments (`make test-qt5`,
  `make test-qt6`); no local virtualenv required.
