FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OBS_HOST=0.0.0.0 OBS_PORT=8000 PYTHONHASHSEED=0
WORKDIR /srv/observatorio
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 10001 observatorio
COPY --chown=observatorio:observatorio . ./
RUN mkdir -p /srv/observatorio/runtime /srv/observatorio/state && chown -R observatorio:observatorio /srv/observatorio/runtime /srv/observatorio/state
USER observatorio
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD ["python","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"]
CMD ["python","app.py"]
