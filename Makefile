PYTHON = python3
VENV := venv

init:
	$(PYTHON) -m venv $(VENV)

install:
	./$(VENV)/bin/pip install -r requirements.txt

venv: init install
	./$(VENV)/bin/activate

flake8: venv
	flake8 main/
