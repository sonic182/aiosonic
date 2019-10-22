# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = sourcedocs
BUILDDIR      = docs

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

test:
	echo "TEST PYTHON 3.6"
	docker run -it --rm -v $(shell pwd):/app python:3.6 bash -l -c "cd /root && cp -r /app/* . && pip install -r requirements.txt && pip install -e \".[test]\" && pytest"
	echo "TEST PYTHON 3.7"
	docker run -it --rm -v $(shell pwd):/app python:3.7 bash -l -c "cd /root && cp -r /app/* . && pip install -r requirements.txt && pip install -e \".[test]\" && pytest"

clear:
	-rm -r $(shell find . -name __pycache__) build dist .mypy_cache aiosonic.egg-info .eggs

build: clear
	python setup.py sdist bdist_wheel

upload_pypi: build
	twine upload dist/*

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
