#!/bin/bash
# kibana-502-diagnose.sh
# Kibana 502 Bad Gateway 원인 진단 스크립트

NAMESPACE="elastic-stack"

echo "🔍 1. Kibana Pod 상태 확인"
kubectl get pods -n $NAMESPACE -l common.k8s.elastic.co/type=kibana -o wide

echo -e "\n🔍 2. Elasticsearch Pod 상태 확인"
kubectl get pods -n $NAMESPACE -l common.k8s.elastic.co/type=elasticsearch -o wide

echo -e "\n🔍 3. Kibana Pod Ready 상태 실시간 확인 (5초)"
kubectl get pods -n $NAMESPACE -l common.k8s.elastic.co/type=kibana -w --no-headers &
sleep 5
kill $!

echo -e "\n🔍 4. Kibana 로그에서 에러 패턴 확인"
KIBANA_POD=$(kubectl get pods -n $NAMESPACE -l common.k8s.elastic.co/type=kibana -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n $NAMESPACE $KIBANA_POD | grep -iE "error|unable|fail|connect" | tail -n 20

echo -e "\n🔍 5. Ingress-NGINX 관련 Kibana 라우팅 로그 확인"
INGRESS_POD=$(kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n ingress-nginx $INGRESS_POD | grep -i kibana | tail -n 20

echo -e "\n💡 TIP:"
echo " - Kibana Pod가 Ready 1/1 되기 전에 접속하면 502가 납니다."
echo " - Kibana 로그에서 Elasticsearch 연결 실패 메시지가 있으면 ES 설정을 먼저 확인하세요."
echo " - NGINX 타임아웃 문제라면 Ingress에 proxy-read-timeout, proxy-send-timeout을 300으로 늘리세요."
