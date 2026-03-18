#!/bin/sh

set -e

python3 -m venv env

./env/bin/python -m pip install -r requirements.txt pytest black pylint

export PYLINTHOME="$(pwd)/.pylint.d"
mkdir -p "$PYLINTHOME"

if ! ./env/bin/pytest; then
   echo -e "\e[31mpytest error!\e[0m"
   exit 1
fi

if ! ./env/bin/pylint $(git ls-files '*.py'); then
   echo "\e[31mpylint error!\e[0m"
   exit 1
fi

if ! ./env/bin/black --check $(git ls-files '*.py'); then
   echo "\e[31mFormatting error!\e[0m"
   echo "Run ./env/bin/black --check $(git ls-files '*.py') to fix"
   exit 1
fi

echo "\n\e[32mAll checks passed!\e[0m"
