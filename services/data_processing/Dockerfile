FROM python:3.14-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8009

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8009"]
