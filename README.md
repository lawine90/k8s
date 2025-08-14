로컬 머신에 k8s 클러스터를 생성, ES와 Kibana를 띄우는 연습

1. 로컬 테스트용 k8s 클러스터 생성하기
- method: kind
```Bash
# kind 설치
brew install kind kubectl helm

# docker 실행 및 DOCKER_HOST 환경변수 설정
sudo systemlctl start docker
ls -l /var/run/docker.sock
export DOCKER_HOST=unix:///var/run/docker.sock

#  kind로 클러스터 생성 --name: 클러스터 이름 설정
kind create cluster --name local-k8s --config ./_k8s/kind-config.yaml
Creating cluster "local-k8s" ...
 ✓ Ensuring node image (kindest/node:v1.33.1) 🖼 
 ✓ Preparing nodes 📦 📦 📦  
 ✓ Writing configuration 📜 
 ✓ Starting control-plane 🕹️ 
 ✓ Installing CNI 🔌 
 ✓ Installing StorageClass 💾 
 ✓ Joining worker nodes 🚜 
Set kubectl context to "kind-local-k8s"
You can now use your cluster with:

kubectl cluster-info --context kind-local-k8s

# 생성된 클러스터 정보 확인
kubectl cluster-info
Kubernetes control plane is running at https://127.0.0.1:58716
CoreDNS is running at https://127.0.0.1:58716/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy
```

2. ECK(Elastic Cloud on Kubernetes) 오퍼레이터 설치
```Bash
# helm으로 클러스터에 eck 오퍼레이터 설치
helm repo add elastic https://helm.elastic.co
helm repo update
helm upgrade --install eck-operator elastic/eck-operator \
  -n elastic-system --create-namespace
```

3. yaml로 es 적용 후 테스트
```Bash
# yaml에 정의한 설정으로 설치
kubectl apply -f ./_k8s/elastic.yaml 

# 정상 설치 확인
kubectl get ns  
NAME                 STATUS   AGE
default              Active   16m
elastic-stack        Active   112s
elastic-system       Active   10m
kube-node-lease      Active   16m
kube-public          Active   16m
kube-system          Active   16m
local-path-storage   Active   16m

kubectl get pods -n elastic-stack
NAME                         READY   STATUS    RESTARTS   AGE
es-cluster-es-default-0      1/1     Running   0          2m16s
kibana-kb-7d778cdcdb-lxq2m   1/1     Running   0          2m15s

kubectl get elasticsearch,kibana -n elastic-stack                 
NAME                                                    HEALTH   NODES   VERSION   PHASE   AGE
elasticsearch.elasticsearch.k8s.elastic.co/es-cluster   green    1       8.14.3    Ready   3m6s

NAME                                  HEALTH   NODES   VERSION   AGE
kibana.kibana.k8s.elastic.co/kibana   green    1       8.14.3    3m6s

# elastic pw 확인
kubectl -n elastic-stack get secret es-cluster-es-elastic-user \
  -o go-template='{{.data.elastic | base64decode }}'
  
# es 포트포워딩
kubectl -n elastic-stack port-forward svc/es-cluster-es-http 9200:9200

# 다른 터미널에서 접속 확인
curl -u elastic:<password> http://localhost:9200/_cluster/health\?pretty
{
  "cluster_name" : "es-cluster",
  "status" : "green",
  "timed_out" : false,
  "number_of_nodes" : 1,
  "number_of_data_nodes" : 1,
  "active_primary_shards" : 31,
  "active_shards" : 31,
  "relocating_shards" : 0,
  "initializing_shards" : 0,
  "unassigned_shards" : 0,
  "delayed_unassigned_shards" : 0,
  "number_of_pending_tasks" : 0,
  "number_of_in_flight_fetch" : 0,
  "task_max_waiting_in_queue_millis" : 0,
  "active_shards_percent_as_number" : 100.0
}
```