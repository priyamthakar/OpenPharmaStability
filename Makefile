.PHONY: help fresh clean recompile install test regen-check

PYTHON ?= python
PYTEST ?= $(PYTHON) -m pytest
REGEN ?= $(PYTHON) tools/regen_expected.py

# Canonical "I don't trust my environment" command.
# - Deletes __pycache__/ and .pyc outside .venv
# - Removes .pytest_cache
# - Byte-compiles all sources (-f forces rewrite)
# - Reinstalls in editable mode with dev deps
# - Runs the full test suite
fresh: clean recompile install test

clean:
	find . -path ./.venv -prune -o -type d -name '__pycache__' -print0 | xargs -0 rm -rf
	find . -path ./.venv -prune -o -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0 | xargs -0 rm -f
	rm -rf .pytest_cache

recompile:
	$(PYTHON) -m compileall -f openpharmastability tools validation

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTEST) -q

# Independent validator: recompute the golden file from scratch
# (pure-numpy) and compare against the on-disk copy. Exits 0 if
# the engine still agrees.
regen-check:
	$(REGEN) --check

help:
	@echo "OpenPharmaStability v1.1.0 Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  fresh        clean + recompile + install + test (canonical reset)"
	@echo "  clean        remove __pycache__/, .pyc, .pytest_cache outside .venv"
	@echo "  recompile    byte-compile all sources with -f"
	@echo "  install      pip install -e .[dev]"
	@echo "  test         run pytest -q"
	@echo "  regen-check  run tools/regen_expected.py --check"
	@echo ""
	@echo "Variables (override on the command line):"
	@echo "  PYTHON=$(PYTHON)"
	@echo "  PYTEST=$(PYTEST)"
