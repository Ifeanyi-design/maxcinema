# 1. Use Python 3.10
FROM python:3.10

# 2. Set working folder
WORKDIR /code

# 3. Copy requirements and install
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 4. Copy ALL files
COPY . .

# 5. CRITICAL FIX: Give permission to the WHOLE folder
# This allows Flask to read/write the DB in the root folder
RUN chmod -R 777 /code

# 6. Run the app
CMD ["gunicorn", "-b", "0.0.0.0:7860", "run:app"]
