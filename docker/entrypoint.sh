#!/usr/bin/env bash
# Install editable sibling libraries, then run the given command under xvfb.
set -euo pipefail

LIBS_DIR="${LIBS_DIR:-/libs}"
PLUGIN_DIR="${PLUGIN_DIR:-/plugin}"

cd "${PLUGIN_DIR}"

# Prefer the QGIS-bundled Python.
PYTHON_BIN="${PYTHON_BIN:-python3}"

install_editable() {
    local path="$1"
    if [[ -d "${path}" && -f "${path}/pyproject.toml" ]]; then
        echo "Installing editable: ${path}"
        "${PYTHON_BIN}" -m pip install -e "${path}" --quiet --no-deps \
            --no-build-isolation
    else
        echo "Skipping missing dependency path: ${path}"
    fi
}

# Install the CRS helper and core survey library first, then optional adapters.
install_editable "${LIBS_DIR}/openroland-crs"
install_editable "${LIBS_DIR}/openroland-survey-core"
install_editable "${LIBS_DIR}/openroland-cube"
install_editable "${LIBS_DIR}/openroland-rw5"
install_editable "${LIBS_DIR}/openroland-jxl"

# Make the plugin package importable without a formal install.
export PYTHONPATH="${PLUGIN_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

if command -v xvfb-run >/dev/null 2>&1; then
    exec xvfb-run -a "$@"
fi

exec "$@"
