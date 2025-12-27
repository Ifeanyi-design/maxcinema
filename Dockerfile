# Use Python 3.10
FROM python:3.10

# Set working directory
WORKDIR /code

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of the app
COPY . .

# Grant permissions (Important for SQLite backup file)
RUN chmod -R 777 /code

# Tell Hugging Face we are listening on 7860
EXPOSE 7860

# Start Gunicorn on Port 7860 with a 10-minute timeout
CMD ["gunicorn", "-b", "0.0.0.0:7860", "--timeout", "600", "run:app"]
