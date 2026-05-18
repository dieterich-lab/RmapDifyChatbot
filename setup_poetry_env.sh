#!/usr/bin/env bash
# This script reproduces the Poetry environment setup for this project.
# It is intentionally verbose and commented so you can learn each step.

set -euo pipefail

# 1) Move to the project directory (where dify_upload.py lives).
PROJECT_DIR="/home/pwiesenbach/rmap-chatbot"
cd "$PROJECT_DIR"

# 2) Check if Poetry is available.
#    If this fails, install Poetry first: https://python-poetry.org/docs/#installation
if ! command -v poetry >/dev/null 2>&1; then
  echo "Error: poetry not found in PATH."
  exit 1
fi

# 3) Show tool versions so you know which interpreter/setup is being used.
poetry --version
python3 --version

# 4) Configure Poetry to create the virtual environment inside the project as .venv.
#    --local writes this setting into poetry.toml in the current project.
poetry config virtualenvs.in-project true --local

# 5) Initialize pyproject.toml if it does not exist yet.
#    We define:
#      - project name: rmap-chatbot
#      - python constraint: ^3.11
#      - dependency: requests
if [[ ! -f pyproject.toml ]]; then
  poetry init \
    # --name: Sets the package/project name written to pyproject.toml.
    --name rmap-chatbot \
    # --python: Declares compatible Python versions for this project.
    --python "^3.11" \
    # --dependency: Adds an initial runtime dependency.
    --dependency requests \
    # --no-interaction: Runs non-interactively (no prompts).
    --no-interaction
else
  echo "pyproject.toml already exists - skipping poetry init."
fi

# 6) Ensure requests exists in dependencies (safe to run repeatedly).
#    If it's already present, Poetry keeps it consistent.
poetry add requests

# 7) Install dependencies into .venv.
#    --no-root means "install dependencies only", not the current project as a package.
poetry install --no-root

# 8) Validate the environment by importing requests and printing interpreter path.
poetry run python -c "import sys, requests; print('Python:', sys.executable); print('requests:', requests.__version__)"

# 9) Example command to run your uploader.
echo "Run uploader with: poetry run python dify_upload.py"
