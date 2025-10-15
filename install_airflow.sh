# ====== 설정 값 ======
AIRFLOW_HOST="${AIRFLOW_HOST:-local-airflow.duckdns.org}"
AIRFLOW_VERSION="${AIRFLOW_VERSION:-2.10.2}"

# install airflow
echo ">>> [4/6] 애플리케이션 네임스페이스 및 es, kibana 설치"
kubectl apply -f ./_k8s/airflow.yaml
