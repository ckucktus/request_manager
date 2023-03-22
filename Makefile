SOURCE_DIR=src
TESTS_DIR=tests
LINE_LENGTH=120

# PRE-COMMIT

pre-commit:
	pre-commit run --show-diff-on-failure

pre-commit-all:
	pre-commit run --all-files --show-diff-on-failure

pre-commit-hooks:
	poetry run pre-commit run --all-files check-added-large-files
	poetry run pre-commit run --all-files check-merge-conflict
	poetry run pre-commit run --all-files detect-private-key
	poetry run pre-commit run --all-files check-json
	poetry run pre-commit run --all-files check-toml
	poetry run pre-commit run --all-files check-yaml
	poetry run pre-commit run --all-files double-quote-string-fixer
	poetry run pre-commit run --all-files end-of-file-fixer
	poetry run pre-commit run --all-files name-tests-test
	poetry run pre-commit run --all-files trailing-whitespace

# CI

ci-check: isort-check black-check ruff-ci mypy test

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

lint: isort-check ruff mypy black-check

ruff-ci:
	poetry run ruff check $(SOURCE_DIR)

ruff:
	poetry run ruff check $(SOURCE_DIR) --config .pre-commit-ruff.toml

mypy:
	poetry run mypy --pretty -p $(SOURCE_DIR)

# SECURITY

security: safety bandit

bandit:
	poetry run bandit -r ./$(SOURCE_DIR)

safety:
	poetry run safety --disable-optional-telemetry-data check --full-report --file poetry.lock

# TESTS

test:
	PYTHONPATH=$(SOURCE_DIR) poetry run pytest -vv

test-ci:
	PYTHONPATH=$(SOURCE_DIR) poetry run pytest --cov=$(SOURCE_DIR) --cov-config=$(TESTS_DIR)/coverage.ini --junitxml=report.xml -vv $(TESTS_DIR)/

test-with-coverage:
	PYTHONPATH=$(SOURCE_DIR) poetry run pytest --cov=$(SOURCE_DIR) --cov-config=$(TESTS_DIR)/coverage.ini -vv

# APP HELPERS

run:
	poetry run python3.8 $(SOURCE_DIR)/main.py

# UTILS

clean: clean-test clean-mypy

clean-test:
	rm -f .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .cache/

clean-mypy:
	rm -rf .mypy_cache
