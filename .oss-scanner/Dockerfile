FROM python:3.12-bookworm
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir poetry
COPY . /src
WORKDIR /src
RUN poetry install --no-interaction
RUN cd tests && npm ci
RUN poetry run ruff check aiosonic tests aiosonic_utils
RUN poetry run py.test
