# Agent notes

This repository adheres to:

- https://github.com/TNick/repository-specs/tree/v1.1.0/qgis-plugin

Read the profile and its complete transitive `spec.toml` inheritance graph
before changing the repository. Read applicable numbered records in `design/`.

Design records: public

## Changelog

Before finishing a task that changed production code (application or library
source—not tests), update the nearest `CHANGELOG.md` under `## [Unreleased]`.

## Testing

There is no local virtualenv in this repository. Run tests through Docker:

```text
make test
make test-qt5
make test-qt6
```

Sibling libraries under `../` (`openroland-survey-core`, and optionally cube/rw5/jxl)
are mounted into containers as `/libs` and installed editable by the
entrypoint.
