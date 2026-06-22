#!/usr/bin/env bash
# Script de construccion para Render
set -o errexit   # sale si hay algun error

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

