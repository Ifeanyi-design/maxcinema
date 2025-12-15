# 1. Use Python 3.10
FROM python:3.10

# 2. Set the working folder inside the container
WORKDIR /code

# 3. Copy requirements and install
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 4. Copy the rest of the project
COPY . .

# 5. Create the instance folder (if it didn't copy) and fix permissions
# We need to give the 'user' permission to write to the DB folder
RUN mkdir -p /code/instance
RUN chmod -R 777 /code/instance

# 6. Run the app
# "run:app" works because you have a file named "run.py" with a variable "app"
CMD ["gunicorn", "-b", "0.0.0.0:7860", "run:app"]