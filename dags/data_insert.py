from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import os
import pymysql


def insert_to_mysql():
    conn = pymysql.connect(
        host=os.environ.get("MYSQL_HOST"),
        port=int(os.environ.get("MYSQL_PORT")),
        user=os.environ.get("MYSQL_USER"),
        password=os.environ.get("MYSQL_PASSWORD"),
        database=os.environ.get("MYSQL_DATABASE"),
    )

    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sample_table (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("INSERT INTO sample_table (name) VALUES ('Airflow Test Data');")
    conn.commit()
    cursor.close()
    conn.close()


with DAG(
        dag_id="insert_to_mysql_dag",
        start_date=datetime(2025, 10, 16),
        schedule_interval=None,  # 수동 실행
        catchup=False,
        tags=["mysql", "example"],
) as dag:

    PythonOperator(
        task_id="insert_data",
        python_callable=insert_to_mysql,
    )
