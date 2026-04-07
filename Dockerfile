# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Upgrade pip to ensure the latest formats are supported
RUN pip install --no-cache-dir --upgrade pip

# Copy dependencies file first for better Docker layer caching
COPY requirements.txt .

# Install dependencies (ignoring errors about proxies during pip install if any, caching securely)
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files into the container
COPY . .

# Ensure start.sh has execution permissions and remove any Windows carriage returns
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# The free tier of Render assigns a random PORT during runtime.

# Exposing 8000 locally, but we rely on the dynamic $PORT dynamically in our start.sh config.
EXPOSE 8000

# Start script
CMD ["./start.sh"]
