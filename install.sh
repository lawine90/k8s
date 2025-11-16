# ====== 설정 값 ======
CLUSTER_NAME="${CLUSTER_NAME:-local-k8s}"
ES_HOST="${ES_HOST:-local-es.duckdns.org}"
KIBANA_HOST="${KIBANA_HOST:-local-kibana.duckdns.org}"
ES_VERSION="${ES_VERSION:-8.14.3}"
AIRFLOW_HOST="${AIRFLOW_HOST:-local-airflow.duckdns.org}"
AIRFLOW_VERSION="${AIRFLOW_VERSION:-2.10.2}"

### kind cluster create
echo ">>> [1/6] kind 클러스터 생성: ${CLUSTER_NAME}"

# brew install
brew install kind kubectl helm

# docker host env set
sudo systemlctl start docker
ls -l /var/run/docker.sock
export DOCKER_HOST=unix:///var/run/docker.sock

# create cluster
if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  kind create cluster --name "${CLUSTER_NAME}" --config ./_k8s/kind-config.yaml
else
  echo " - kind 클러스터 '${CLUSTER_NAME}' 이미 존재 → 건너뜀"
fi

# check cluster status
kubectl cluster-info --context kind-local-k8s

# install ingress
echo ">>> [2/6] NGINX Ingress Controller 설치 (kind 전용 매니페스트)"
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.9.1/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=Available deploy/ingress-nginx-controller \
  --timeout=120s

### install es with ECK operator
# install eck operator
echo ">>> [3/6] ECK(Elastic Cloud on Kubernetes) 오퍼레이터 설치 (Helm)"
helm repo add elastic https://helm.elastic.co
helm repo update
helm upgrade --install eck-operator elastic/eck-operator \
  -n elastic-system --create-namespace

# install es & kibana
echo ">>> [4/6] 애플리케이션 네임스페이스 및 es, kibana 설치"
kubectl apply -f ./_k8s/elastic.yaml
kubectl wait -n elastic-stack --for=condition=Ready elasticsearch/es-cluster --timeout=10m
kubectl wait -n elastic-stack --for=condition=Ready kibana/kibana --timeout=10m

# elastic pw 조회
echo ">>> [5/6] elastic 사용자 비밀번호 조회"
ES_PW="$(kubectl -n elastic-stack get secret es-cluster-es-elastic-user -o go-template='{{.data.elastic | base64decode }}')"
echo " - elastic 비밀번호: ${ES_PW}"

# airflow 설치
echo ">>> [6/6] airflow 설치"
kubectl apply -f ./_k8s/airflow.yaml


echo ">>> 접속 정보 요약"
cat <<INFO

[도메인 매핑 필수: /etc/hosts]
  127.0.0.1 ${ES_HOST}
  127.0.0.1 ${KIBANA_HOST}

[접속]
  Kibana:   http://${KIBANA_HOST}
    - 로그인: elastic / ${ES_PW}

  Elasticsearch (HTTP, 인증 필요):
    - 브라우저:  http://${ES_HOST}
    - curl:      curl -u elastic:${ES_PW} http://${ES_HOST}/_cluster/health?pretty

[문제 해결]
  - Ingress 동작 확인:
      kubectl get ingress -n elastic-stack
      kubectl describe ingress kibana -n elastic-stack
  - Pod 상태:
      kubectl -n elastic-stack get pods
  - Kibana 포트포워딩(임시):
      kubectl -n elastic-stack port-forward svc/kibana-kb-http 5601:5601
INFO