FROM ubuntu:24.04
WORKDIR /app
COPY . /app
COPY supervisord.conf /etc/supervisord.conf
RUN apt-get update && apt-get install -y python3-pip python3.12-venv \
    && python3 -m venv .venv \
    && source .venv/bin/activate \
    && pip3 install supervisor \
    && pip3 install -r requirements.txt \
    && pip3 install gunicorn uvicorn \
    && chmod +x entrypoint.sh \
    && chmod +x flask.sh \
    && chmod +x backend.sh
EXPOSE 5001
ENV PYTHONPATH "${PYTHONPATH}:/app"
ENV PATH "${PATH}:/app"
ENTRYPOINT ["./entrypoint.sh"]