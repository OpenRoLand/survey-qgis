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
    && python3 -m venv --system-site-packages /opt/survey-qgis-venv \
    && /opt/survey-qgis-venv/bin/python -m pip install --no-cache-dir --upgrade pip \
    && /opt/survey-qgis-venv/bin/python -m pip install --no-cache-dir \
        "setuptools>=77" "wheel" "packaging>=24.2" \
        "attrs>=23.1,<25" "httpx>=0.27,<1" "numpy>=1.26,<3" \
        "openpyxl>=3.1,<4" "platformdirs>=4.2,<5" "pyproj>=3.6,<4" \
        "rasterio>=1.3,<2" "sqlalchemy>=2.0,<3" "ezdxf>=1.0,<2" \
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
