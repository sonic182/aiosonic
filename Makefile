
all: test


test:
	docker run -it --rm -v $(shell pwd):/app python:3.5 bash -l -c "cd /app && pip install -e \".[test]\" && pytest"
	docker run -it --rm -v $(shell pwd):/app python:3.6 bash -l -c "cd /app && pip install -e \".[test]\" && pytest"
	docker run -it --rm -v $(shell pwd):/app python:3.7 bash -l -c "cd /app && pip install -e \".[test]\" && pytest"
	rm -r htmlcov/
