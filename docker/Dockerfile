# Dockerfile for running survey-qgis tests against a QGIS image.
#
# Build args:
#   QGIS_IMAGE - base image tag (Qt5 or Qt6 QGIS desktop image)

ARG QGIS_IMAGE=qgis/qgis:ltr-noble
FROM ${QGIS_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV QT_QPA_PLATFORM=offscreen
ENV PYTHONUNBUFFERED=1

# Install test dependencies in an isolated environment because recent Ubuntu
# QGIS images mark the system interpreter as externally managed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/survey-qgis-venv \
    && /opt/survey-qgis-venv/bin/python -m pip install --no-cache-dir --upgrade pip \
    && /opt/survey-qgis-venv/bin/python -m pip install --no-cache-dir \
        "setuptools>=77" "wheel" \
    && /opt/survey-qgis-venv/bin/python -m pip install --no-cache-dir \
        "pytest==9.1.1" \
        "pytest-cov==7.1.0" \
        "pytest-qgis==4.0.1"
ENV PATH="/opt/survey-qgis-venv/bin:${PATH}"

WORKDIR /plugin

COPY docker/entrypoint.sh /usr/local/bin/survey-qgis-entrypoint.sh
RUN chmod +x /usr/local/bin/survey-qgis-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/survey-qgis-entrypoint.sh"]
CMD ["pytest", "-q"]
