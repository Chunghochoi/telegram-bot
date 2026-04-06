<<<<<<< HEAD
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble
=======
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy
>>>>>>> 6f07c3f14263c1b12a79bc49d3bc4304512ea031

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

<<<<<<< HEAD
=======
RUN playwright install chromium

>>>>>>> 6f07c3f14263c1b12a79bc49d3bc4304512ea031
COPY extensions/rektCaptcha.zip extensions/rektCaptcha.zip
RUN python3 -c "import zipfile; zipfile.ZipFile('extensions/rektCaptcha.zip').extractall('extensions/rektCaptcha')" \
    && rm extensions/rektCaptcha.zip

COPY bot.py .

CMD ["python3", "bot.py"]
