FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY extensions/rektCaptcha.zip extensions/rektCaptcha.zip
RUN python3 -c "import zipfile; zipfile.ZipFile('extensions/rektCaptcha.zip').extractall('extensions/rektCaptcha')" \
    && rm extensions/rektCaptcha.zip

COPY bot.py .

CMD ["python3", "bot.py"]
