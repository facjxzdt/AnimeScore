FROM ubuntu:22.04
WORKDIR /app
COPY . /app
RUN apt-get update && apt-get install -y python3 python3-pip \
    && pip3 install -r requirements.txt \
EXPOSE 5001
CMD ["python3", "app.py"]
