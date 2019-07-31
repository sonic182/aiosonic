
all: test


test:
	echo "TEST PYTHON 3.5"
	docker run -it --rm -v $(shell pwd):/app python:3.5 bash -l -c "cd /app && pip install -e \".[test]\" && pytest"
	echo "TEST PYTHON 3.6"
	docker run -it --rm -v $(shell pwd):/app python:3.6 bash -l -c "cd /app && pip install -e \".[test]\" && pytest"
	echo "TEST PYTHON 3.7"
	docker run -it --rm -v $(shell pwd):/app python:3.7 bash -l -c "cd /app && pip install -e \".[test]\" && pytest"
