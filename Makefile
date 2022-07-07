# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = sourcedocs
BUILDDIR      = docs
DOCKER_CMD		= curl -sL https://deb.nodesource.com/setup_14.x | bash && apt-get update && apt-get install nodejs -y && cd /root && cp -r /app/* . && pip install -r requirements.txt && pip install -e \".[test]\" && pytest

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)


test37:
	echo "TEST PYTHON 3.7"
	docker run -i --rm -v $(shell pwd):/app python:3.7 bash -l -c "$(DOCKER_CMD)"

test38:
	echo "TEST PYTHON 3.8"
	docker run -i --rm -v $(shell pwd):/app python:3.8 bash -l -c "$(DOCKER_CMD)"

tes39:
	echo "TEST PYTHON 3.9"
	docker run -i --rm -v $(shell pwd):/app python:3.9 bash -l -c "$(DOCKER_CMD)"

test: test37 test38 test39
	echo "OK"

clear:
	-rm -r $(shell find . -name __pycache__) build dist .mypy_cache aiosonic.egg-info .eggs

build: clear
	python setup.py sdist

upload_pypi: build
	twine upload dist/*

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
