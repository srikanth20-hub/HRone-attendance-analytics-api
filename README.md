# Employee Attendance & Analytics API

A FastAPI and MongoDB backend for employee management, attendance tracking, manual attendance corrections with an audit trail, and analytics using MongoDB aggregation pipelines.

## Requirements

- Python 3.11+
- MongoDB 6.0 or newer
- Git

## Setup

1. Create and activate a Python virtual environment.

2. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure the following environment variables:

   - `MONGO_URI` — MongoDB connection URI
   - `MONGO_DB` — MongoDB database name

   You can use a local `.env` file for development. Do not commit credentials or `.env` files.

4. From the project root, start the application:

   ```bash
   python -m uvicorn app.main:app --reload --port 8001
   ```

## API Documentation

When the application is running:

- Health check: http://127.0.0.1:8001/health
- Interactive API documentation: http://127.0.0.1:8001/docs

## Notes

- MongoDB indexes are created when the application starts.
- Attendance endpoints enforce business rules and support manual corrections.
- Analytics endpoints use MongoDB aggregation pipelines.
- Never commit `.env` files, credentials, secrets, virtual environments, or database dumps to the public repository.