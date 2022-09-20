SOURCE_DIR=src
TESTS_DIR=tests
LINE_LENGTH=120

# PRE-COMMIT

pre-commit:
	pre-commit run --show-diff-on-failure

pre-commit-all:
	pre-commit run --all-files --show-diff-on-failure

# CI

ci-check: isort-check black-check flake8 mypy test

# FORMATTERS

formatters: isort black

isort:
	poetry run isort $(SOURCE_DIR)
	poetry run isort $(TESTS_DIR)

isort-check:
	poetry run isort $(SOURCE_DIR) --diff --color --check-only
	poetry run isort $(TESTS_DIR) --diff --color --check-only

black:
	poetry run black $(SOURCE_DIR) $(TESTS_DIR)

black-check:
	poetry run black $(SOURCE_DIR) $(TESTS_DIR) --check

# LINTERS

lint: isort-check flake8 mypy

flake8:
	poetry run flake8 $(SOURCE_DIR)
	poetry run flake8 --ignore=Q $(TESTS_DIR)

mypy:
	poetry run mypy --pretty -p $(SOURCE_DIR)

# SECURITY

security: safety bandit

bandit:
	poetry run bandit -r ./$(SOURCE_DIR)

safety:
	poetry run safety check --full-report

# TESTS

test:
	PYTHONPATH=$(SOURCE_DIR) poetry run pytest -vv

test-ci:
	PYTHONPATH=$(SOURCE_DIR) poetry run pytest --cov=$(SOURCE_DIR) --cov-config=$(TESTS_DIR)/coverage.ini --junitxml=report.xml -vv ${TESTS_DIR}/

test-with-coverage:
	PYTHONPATH=$(SOURCE_DIR) poetry run pytest --cov=$(SOURCE_DIR) --cov-config=$(TESTS_DIR)/coverage.ini -vv

# APP HELPERS

run:
	poetry run python $(SOURCE_DIR)/main.py

# UTILS

clean: clean-test clean-mypy

clean-test:
	rm -f .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .cache/

clean-mypy:
	rm -rf .mypy_cache