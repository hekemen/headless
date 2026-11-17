PYTHON ?= python3
VENV   := venv
PIP    := $(VENV)/bin/pip

.PHONY: venv install clean

venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv
	$(PIP) install -r requirements.txt

clean:
	rm -rf $(VENV)