# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = sourcedocs
BUILDDIR      = docs

# Default Docker command for CPython
DOCKER_CMD = curl -sL https://deb.nodesource.com/setup_20.x | bash \
	&& apt-get update \
	&& apt-get install -y nodejs \
	&& cd /root \
	&& cp -r /app/* . \
	&& pip install poetry \
	&& poetry install \
	&& poetry run py.test

# Separate Docker command for PyPy
# Installs an up-to-date Rust toolchain with rustup (rather than older distro cargo/rustc).
# Also upgrades pip/setuptools/wheel/maturin to avoid potential parse issues.
DOCKER_CMD_PYPY = curl -sL https://deb.nodesource.com/setup_20.x | bash \
	&& apt-get update \
	&& apt-get install -y nodejs curl build-essential \
	&& curl https://sh.rustup.rs -sSf | sh -s -- -y \
	&& . /root/.cargo/env \
	&& cd /root \
	&& cp -r /app/* . \
	&& pip install poetry \
	&& poetry install \
	&& poetry run py.test

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

test310:
	echo "TEST PYTHON 3.10"
	docker run -i --rm -v $(shell pwd):/app python:3.10 bash -c "$(DOCKER_CMD)"

test311:
	echo "TEST PYTHON 3.11"
	docker run -i --rm -v $(shell pwd):/app python:3.11 bash -c "$(DOCKER_CMD)"

test312:
	echo "TEST PYTHON 3.12"
	docker run -i --rm -v $(shell pwd):/app python:3.12 bash -c "$(DOCKER_CMD)"

test313:
	echo "TEST PYTHON 3.13"
	docker run -i --rm -v $(shell pwd):/app python:3.13 bash -c "$(DOCKER_CMD)"

test-pypy310:
	echo "TEST PYPY 3.10"
	docker run -i --rm -v $(shell pwd):/app pypy:3.10 bash -c "$(DOCKER_CMD_PYPY)"

test: test310 test311 test312 test313 test-pypy39 test-pypy310
	echo "OK"

clear:
	-rm -r $(shell find . -name __pycache__) build dist .mypy_cache aiosonic.egg-info .eggs

build: clear
	poetry build

upload_pypi: build
	twine upload dist/*

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
