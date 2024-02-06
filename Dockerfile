FROM ubuntu:22.04
WORKDIR /app
COPY . /app
RUN apt-get update && apt-get install -y python3 python3-pip cron \
    && pip install virtualenv \
    && virtualenv venv \
    && . venv/bin/activate \
    && pip3 install -r requirements.txt \
    && chmod +x entrypoint.sh \
ADD ./cron.txt /etc/cron.d/
EXPOSE 5001
ENV PYTHONPATH "${PYTHONPATH}:/app"
ENV PATH "${PATH}:/app"
ENTRYPOINT ["./entrypoint.sh"]