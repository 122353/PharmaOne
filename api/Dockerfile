FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Keep runtime assets alongside the application code. PharmaMatch /
# PharmaClassify load checked-in JSON artifacts, and the explicit migration
# runner reads the SQL files from /app/migrations.
COPY app ./app
COPY model_artifacts ./model_artifacts
COPY migrations ./migrations

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
