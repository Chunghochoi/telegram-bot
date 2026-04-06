FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

COPY extensions/rektCaptcha.zip extensions/rektCaptcha.zip
RUN python3 -c "import zipfile; zipfile.ZipFile('extensions/rektCaptcha.zip').extractall('extensions/rektCaptcha')" \
    && rm extensions/rektCaptcha.zip

COPY bot.py .

CMD ["python3", "bot.py"]
