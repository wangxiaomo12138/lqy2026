FROM python:3.12-slim
WORKDIR /app
COPY tune-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY tune-engine/app ./app
COPY tune-engine/scripts ./scripts
RUN mkdir -p data
EXPOSE 8100
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
