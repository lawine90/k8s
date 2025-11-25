# 1. 베이스 이미지 선택 (가벼운 Python 3.10)
FROM python:3.10-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. (중요) requirements.txt 먼저 복사 및 설치
# (이 파일이 변경되지 않으면 Docker는 이 단계를 캐시하여 빌드 속도 향상)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 모델과 소스코드 복사
# (FastAPI 앱 코드 복사)
COPY ../autocomplete/main.py .
## (모델 폴더 복사) <- k8s cluster 내부에 띄운 minIO로 대체
#COPY ./model ./model

# 5. 서버 포트 노출
EXPOSE 8000

# 6. (중요) 컨테이너가 시작될 때 실행할 명령
# 0.0.0.0 으로 호스트를 지정해야 Docker 외부에서 접속 가능
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]