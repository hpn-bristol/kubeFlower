FROM python:3.9.8-slim-bullseye
WORKDIR /app
RUN /usr/local/bin/python -m pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt
COPY ./src src
CMD ["/bin/sh", "-c", "while sleep 1000; do :; done"]