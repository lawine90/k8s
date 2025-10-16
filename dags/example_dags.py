from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

with DAG(
        dag_id='example_dag',
        start_date=datetime(2024, 1, 1),
        schedule_interval='@daily',
        catchup=False,
) as dag:

    BashOperator(
        task_id='say_hello',
        bash_command='echo "Hello from Airflow DAG!"'
    )
