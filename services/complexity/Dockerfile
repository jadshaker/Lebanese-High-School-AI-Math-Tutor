FROM python:3.14-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Expose port
EXPOSE 8004

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8004"]
