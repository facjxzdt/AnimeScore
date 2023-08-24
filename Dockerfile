FROM ubuntu:22.04
WORKDIR /app
COPY . /app
RUN apt-get update && apt-get install -y python3 python3-pip \
    && pip install virtualenv \
    && virtualenv venv \
    && . venv/bin/activate \
    && pip3 install -r requirements.txt
EXPOSE 5001
CMD [". venv/bin/activate"]
CMD ["python3", "/app/web_api/app.py"]