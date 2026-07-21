# Agent notes

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

Sibling libraries under `../` (`siscadro-survey`, and optionally cube/rw5/jxl)
are mounted into containers as `/libs` and installed editable by the
entrypoint.
