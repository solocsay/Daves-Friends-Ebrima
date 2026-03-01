FROM python:3.13

WORKDIR /app

COPY . .

RUN pip install --use-pep517 .

COPY . .

CMD ["python", "uno.py"]
