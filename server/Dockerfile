FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# --workers 4: see docker-compose.yml's comment / server/README.md's B6
# load-test section — a single worker process can't hit the plan's own
# stated peak traffic target.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
