FROM apache/airflow:2.10.5-python3.9

# 설치 Version
ENV AIRFLOW_VERSION=2.10.5

USER root
RUN apt-get update && apt-get install -y vim && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt