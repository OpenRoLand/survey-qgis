# Makefile for siscadro-survey-qgis.
#
# All testing and development runs through Docker. There is no local venv.

COMPOSE ?= docker compose
PLUGIN_DIR ?= $(CURDIR)

.PHONY: help test test-qt5 test-qt6 shell shell-qt5 shell-qt6 deploy lint

help:
	@echo "Targets:"
	@echo "  make test       - run pytest on Qt5 and Qt6 QGIS images"
	@echo "  make test-qt5   - run pytest on QGIS 3.x LTR (Qt5)"
	@echo "  make test-qt6   - run pytest on QGIS 4.x (Qt6)"
	@echo "  make shell      - interactive shell in the Qt5 container"
	@echo "  make shell-qt5  - interactive shell in the Qt5 container"
	@echo "  make shell-qt6  - interactive shell in the Qt6 container"
	@echo "  make deploy     - copy plugin into QGIS_PLUGIN_DIR (host)"

test: test-qt5 test-qt6

test-qt5:
	$(COMPOSE) run --rm qt5

test-qt6:
	$(COMPOSE) run --rm qt6

shell: shell-qt5

shell-qt5:
	$(COMPOSE) run --rm --entrypoint /bin/bash qt5

shell-qt6:
	$(COMPOSE) run --rm --entrypoint /bin/bash qt6

deploy:
	@if [ -z "$(QGIS_PLUGIN_DIR)" ]; then \
		echo "Set QGIS_PLUGIN_DIR to your QGIS plugins folder"; \
		exit 1; \
	fi
	mkdir -p "$(QGIS_PLUGIN_DIR)/siscadro_survey"
	cp -r __init__.py metadata.txt assets survey_qgis \
		"$(QGIS_PLUGIN_DIR)/siscadro_survey/"
	@echo "Deployed to $(QGIS_PLUGIN_DIR)/siscadro_survey"
