# KoGPT-2 기반 자동완성 API (K8s + MinIO + FastAPI)

### 프로젝트 아키텍처 (MLOps Flow)
- 모델 학습: KoGPT-2로 사용자 검색 로그 데이터 파인튜닝
- 모델 저장: 학습 완료된 모델을 MinIO에 저장
- API 컨테이너: FastAPI 앱이 시작될 때 MinIO에서 모델을 다운로드하여 메모리에 로드
- 배포: Minikube 클러스터에 Deployment, Service, Ingress를 통해 서비스 배포

### 1. KoGPT-2 fine tunning
- GPU를 사용할 수 있으며 google drive에 `keywords.txt`, `bpe-tokenizer.json` 파일이 있다고 가정
- `training.py`를 이용하여 모델 학습

### 2. 환경 설정 및 배포 가이드
- 전제조건: Docker Desktop (or Docker Engine), Minikube, kubectl
- 모델 파일 수동 업로드: 모델 파일을 Docker 이미지에 포함시키지 않으므로 MinIO 서버 배포 후 수동으로 업로드 필요
  - MinIO 접속: `minikube service minio-service -n autocomplete --url` 명령어로 주소를 확인 (Console 포트 9001)
  - minio.yaml에 작성한 id/pw로 로그인 후 버킷 생성 (bucket name: autocomplete)
  - 학습한 모델의 모든 파일을 생성한 버킷 내 `/model` 경로에 업로드
- 배포 스크립트 실행 (`install.sh`)