FROM python:3.12-slim
WORKDIR /app
COPY check-mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY check-mcp/server.py .
EXPOSE 8200
CMD ["python", "server.py"]
