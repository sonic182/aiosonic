# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = sourcedocs
BUILDDIR      = docs
DOCKER_CMD    = curl -sL https://deb.nodesource.com/setup_20.x | bash && apt-get update && apt-get install nodejs -y && cd /root && cp -r /app/* . && pip install poetry && poetry install && poetry run py.test

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

test38:
	echo "TEST PYTHON 3.8"
	docker run -i --rm -v $(shell pwd):/app python:3.8 bash -c "$(DOCKER_CMD)"

test39:
	echo "TEST PYTHON 3.9"
	docker run -i --rm -v $(shell pwd):/app python:3.9 bash -c "$(DOCKER_CMD)"

test310:
	echo "TEST PYTHON 3.10"
	docker run -i --rm -v $(shell pwd):/app python:3.10 bash -c "$(DOCKER_CMD)"

test311:
	echo "TEST PYTHON 3.11"
	docker run -i --rm -v $(shell pwd):/app python:3.11 bash -c "$(DOCKER_CMD)"

test312:
	echo "TEST PYTHON 3.12"
	docker run -i --rm -v $(shell pwd):/app python:3.12 bash -c "$(DOCKER_CMD)"

test-pypy37:
	echo "TEST PYPY 3.7"
	docker run -i --rm -v $(shell pwd):/app pypy:3.7 bash -c "$(DOCKER_CMD)"

test-pypy38:
	echo "TEST PYPY 3.8"
	docker run -i --rm -v $(shell pwd):/app pypy:3.8 bash -c "$(DOCKER_CMD)"

test-pypy39:
	echo "TEST PYPY 3.9"
	docker run -i --rm -v $(shell pwd):/app pypy:3.9 bash -c "$(DOCKER_CMD)"

test-pypy310:
	echo "TEST PYPY 3.10"
	docker run -i --rm -v $(shell pwd):/app pypy:3.10 bash -c "$(DOCKER_CMD)"

test: test37 test38 test39 test310 test311 test312 test-pypy37 test-pypy38 test-pypy39 test-pypy310
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
