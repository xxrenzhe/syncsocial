FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends xvfb fluxbox x11vnc novnc websockify \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV DISPLAY=:99

EXPOSE 9300
EXPOSE 7900

ENTRYPOINT ["/entrypoint.sh"]

