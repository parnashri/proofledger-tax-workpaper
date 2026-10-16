FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.html *.py packet.json ./
COPY static ./static
ENV PYTHONUNBUFFERED=1
ENV PROOFLEDGER_DB=/data/proofledger.sqlite3
EXPOSE 8081
CMD ["python3", "server.py", "--host", "0.0.0.0", "--port", "8081"]
