#!/bin/bash

# --- 설정 변수 ---
MINIKUBE_PROFILE="local-test"
NAMESPACE="autocomplete"
APP_DIR="./was/autocomplete"
IMAGE_NAME="labineseo90/autocomplete-api:v2.2"


echo "==========================================="
echo "MLOps 서비스 (MinIO & API) Minikube 설치 스크립트"
echo "==========================================="


# 1. Minikube 설치 상태 확인
echo "✅ 1. Minikube 클러스터 상태를 확인합니다."
if ! command -v minikube &> /dev/null
then
    echo "Minikube가 설치되어 있지 않습니다."
    brew install minikube
fi

# Minikube k8s cluster 시작
if minikube status -p ${MINIKUBE_PROFILE} | grep "host: Running" &> /dev/null; then
    echo "   Minikube 클러스터 (${MINIKUBE_PROFILE})가 이미 실행 중입니다."
else
    echo "   Minikube 클러스터를 시작합니다..."

    open -a Docker # macOS 전용
    minikube start -p ${MINIKUBE_PROFILE} --driver=docker
    minikube addons enable ingress -p "${MINIKUBE_PROFILE}"

    # shellcheck disable=SC2181
    if [ $? -ne 0 ]; then
        echo "🚨 Minikube 시작에 실패했습니다. 로그를 확인해 주세요."
        exit 1
    fi
fi


# 2. minikube docker 환경 설정
echo ""
echo "✅ 2. Minikube Docker 환경으로 설정합니다."
eval "$(minikube -p ${MINIKUBE_PROFILE} docker-env)"


# 3. docker image build & push
echo ""
echo "✅ 3. Docker 이미지를 빌드합니다: ${IMAGE_NAME}"
# --file: Dockerfile 경로 지정, -t: 태그 지정, .: 빌드 컨텍스트
docker build --file ${APP_DIR}/Dockerfile -t ${IMAGE_NAME} ${APP_DIR}

# shellcheck disable=SC2181
if [ $? -ne 0 ]; then
    echo "🚨 Docker 이미지 빌드에 실패했습니다. Dockerfile을 확인해 주세요."
    # Minikube Docker 환경을 원래대로 복구
    eval "$(minikube docker-env -u)"
    exit 1
fi
echo "   Docker 이미지 빌드 성공."


# 4. K8s 네임스페이스 생성
echo ""
echo "✅ 4. Kubernetes 네임스페이스 '${NAMESPACE}'를 생성합니다."
kubectl create namespace ${NAMESPACE} 2>/dev/null || true # 이미 있으면 무시


# 5. MinIO 배포 (Service, PVC, Deployment)
echo ""
echo "✅ 5. MinIO Deployment를 배포합니다. (PV 포함)"
kubectl apply -f ${APP_DIR}/minio.yaml -n ${NAMESPACE}
echo "MinIO 설치 완료. 모델 파일을 업로드 하세요"


# 6. API 배포 (Deployment, Service)
echo ""
echo "✅ 6. API Deployment를 배포합니다."
# API YAML 파일 내부에 ${IMAGE_NAME} 태그가 사용되었다고 가정
kubectl apply -f ${APP_DIR}/api.yaml -n ${NAMESPACE}


# 7. 배포 상태 확인
echo ""
echo "✅ 7. 모든 Pod가 준비될 때까지 기다립니다. (최대 60초)"
kubectl wait --for=condition=ready pod --all --timeout=60s -n ${NAMESPACE}

# shellcheck disable=SC2181
if [ $? -ne 0 ]; then
    echo "⚠️ 일부 Pod가 Ready 상태가 되지 못했습니다. 'kubectl get pods -n ${NAMESPACE}'로 확인하세요."
else
    echo "🎉 모든 컴포넌트 (MinIO, API) 배포 및 실행 완료"
fi


# 8. Minikube Docker 환경 원래대로 복구 (매우 중요)
echo ""
echo "✅ 8. 로컬 Docker 환경으로 복구합니다."
eval "$(minikube docker-env -u)"

# 9. 접속 정보 출력
echo ""
echo "======================================================"
echo "      🚀 배포 완료 정보 (네임스페이스: ${NAMESPACE}) 🚀"
echo "------------------------------------------------------"
echo "  [Pod 상태]"
kubectl get pods -n ${NAMESPACE}
echo "  [Service 접속 정보 (내부 IP)]"
kubectl get services -n ${NAMESPACE}
echo "------------------------------------------------------"
echo "  [MinIO 접속 팁]"
echo "  MinIO 웹 콘솔 접속을 위해 다음 명령어를 사용하세요: "
echo "  minikube service minio-service -n ${NAMESPACE} --url"
echo "  (port: 9001 - Console, 9000 - API)"
echo "======================================================"