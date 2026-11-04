FROM python:3.12-slim
WORKDIR /app
COPY services/broker/broker.py /app/broker.py
EXPOSE 8082
CMD ["python3", "/app/broker.py"]
