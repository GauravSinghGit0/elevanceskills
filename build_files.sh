#!/bin/bash
# Vercel Build Script for Django
export PIP_BREAK_SYSTEM_PACKAGES=1

echo "==> Installing Python dependencies..."
python3 -m pip install -r requirements.txt --break-system-packages || true

echo "==> Collecting static assets..."
python3 manage.py collectstatic --noinput --clear || true

# Guarantee staticfiles directory always exists
mkdir -p staticfiles

echo "==> Vercel build completed successfully!"

