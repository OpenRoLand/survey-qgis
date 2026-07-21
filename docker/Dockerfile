# Dockerfile for running survey-qgis tests against a QGIS image.
#
# Build args:
#   QGIS_IMAGE - base image tag (Qt5 or Qt6 QGIS desktop image)

ARG QGIS_IMAGE=qgis/qgis:ltr-noble
FROM ${QGIS_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV QT_QPA_PLATFORM=offscreen
ENV PYTHONUNBUFFERED=1

# Ensure pip targets the QGIS Python interpreter.
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir \
        "pytest>=7,<9" \
        "pytest-cov>=4,<7" \
        "pytest-qgis>=1.3,<3"

WORKDIR /plugin

COPY docker/entrypoint.sh /usr/local/bin/survey-qgis-entrypoint.sh
RUN chmod +x /usr/local/bin/survey-qgis-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/survey-qgis-entrypoint.sh"]
CMD ["pytest", "-q"]
