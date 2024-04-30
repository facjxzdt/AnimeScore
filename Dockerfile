FROM ubuntu:22.04
WORKDIR /app
COPY . /app
COPY supervisord.conf /etc/supervisord.conf
RUN apt-get update && apt-get install -y python3 python3-pip libxml2-dev libxslt-dev python3-lxml \
    && pip install virtualenv \
    && pip install gunicorn uvicorn supervisor \
    && virtualenv venv \
    && . venv/bin/activate \
    && pip3 install -r requirements.txt \
    && chmod +x entrypoint.sh
EXPOSE 5001
ENV PYTHONPATH "${PYTHONPATH}:/app"
ENV PATH "${PATH}:/app"
ENTRYPOINT ["./entrypoint.sh"]