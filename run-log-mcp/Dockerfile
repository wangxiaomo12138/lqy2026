FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY run-log-mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared ./shared
COPY run-log-mcp/core.py run-log-mcp/app.py run-log-mcp/server.py ./
RUN mkdir -p /app/data
EXPOSE 8300
CMD ["python", "app.py"]
