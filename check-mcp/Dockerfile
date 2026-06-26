FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY check-mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared ./shared
COPY check-mcp/core.py check-mcp/app.py check-mcp/server.py ./
EXPOSE 8200
CMD ["python", "app.py"]
