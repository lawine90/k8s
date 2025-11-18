# ====== 설정 값 ======
CLUSTER_NAME="${CLUSTER_NAME:-local-test}"
NAMESPACE="${NAMESPACE:-autocomplete}"
API_HOST="${ES_HOST:-local-es.duckdns.org}"
MINIO_HOST="${MINIO_HOST:-minio.autocomplete-api.local}"

### 1. minikube cluster create
# docker host env set
sudo systemlctl start docker
ls -l /var/run/docker.sock
export DOCKER_HOST=unix:///var/run/docker.sock

# brew install
brew install minikube

# start cluster & create ingress
minikube start --driver=docker -p "${CLUSTER_NAME}"
minikube addons enable ingress -p "${CLUSTER_NAME}"

### 2. deploy minio for model storage
kubectl apply -f ./minio.yaml
