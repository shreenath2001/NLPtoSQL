#!/bin/bash
set -e

# Initialize the SQLite demo database dynamically so it's always fresh in the cloud
echo "Creating demo database..."
python database.py

# Default to 8000 if Render does not provide a PORT
PORT=${PORT:-8000}

echo "Starting FastAPI server on Port $PORT..."
# Render passes the listening port securely via the $PORT environment variable.
exec uvicorn main:app --host 0.0.0.0 --port $PORT
