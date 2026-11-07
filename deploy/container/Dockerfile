ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS install
RUN python -m venv /opt/venv
COPY wheels/ /wheels/
RUN /opt/venv/bin/python -m pip install --no-index --no-cache-dir --find-links=/wheels -r /wheels/requirements.txt && /opt/venv/bin/python -m pip check

FROM ${BASE_IMAGE}
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=install /opt/venv /opt/venv
COPY release.json /opt/launchpad/release.json
RUN mkdir -p /data && chown 10001:10001 /data
WORKDIR /data
USER 10001:10001
EXPOSE 8092
CMD ["python", "-m", "uvicorn", "service_desk.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8092"]
