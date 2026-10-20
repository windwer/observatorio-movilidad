FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OBS_HOST=0.0.0.0 OBS_PORT=8000
WORKDIR /srv/observatorio
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 10001 observatorio
COPY --chown=observatorio:observatorio . ./
RUN mkdir -p /srv/observatorio/data && chown -R observatorio:observatorio /srv/observatorio/data
USER observatorio
EXPOSE 8000
CMD ["python","app.py"]
