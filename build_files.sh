#!/bin/bash
# Vercel Build Script for Django
echo "==> Installing Python dependencies..."
python3 -m pip install -r requirements.txt

echo "==> Collecting static assets..."
python3 manage.py collectstatic --noinput --clear

echo "==> Vercel build completed successfully!"
