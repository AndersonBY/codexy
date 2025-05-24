# Pre-commit Configuration Guide

## Overview

This project has pre-commit hooks configured to automatically run code checks and formatting before each git commit.

## Included hooks

1. **ruff lint** - Code quality check with automatic fixes
2. **ruff format** - Code formatting
3. **trailing-whitespace** - Remove trailing whitespace
4. **end-of-file-fixer** - Ensure files end with a newline
5. **check-yaml** - YAML file syntax check
6. **check-added-large-files** - Prevent committing large files

## Usage

### Install dependencies
```bash
pdm install
```

### Install pre-commit hooks
```bash
pdm run pre-commit install
```

### Run all checks manually
```bash
pdm run pre-commit run --all-files
```

### Run specific hook manually
```bash
pdm run pre-commit run ruff-format
```

## Notes

- If pre-commit checks fail, the commit will be blocked
- If code is automatically fixed, you need to `git add` again and commit
- You can use `git commit --no-verify` to skip pre-commit checks (not recommended)
