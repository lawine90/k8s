import os

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import re
import math
import boto3
import torch
import logging
from typing import List, Tuple

from fastapi import FastAPI, Query
from pydantic import BaseModel
from llama_cpp import Llama


# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- 응답 모델 정의 ---
class RelkeyResponse(BaseModel):
    q: str
    p: float
    subkeys: List[str]


# --- 1. FastAPI 앱 정의 ---
app = FastAPI(title="Qwen Related Query API")

# --- 2. 전역 변수 ---
model = None
tokenizer = None

# instruction: 학습 때 사용한 지시문과 동일한 instruction 사용
# INSTRUCTION_TEXT = "다음 검색어와 연관된 키워드를 쉼표(,)로 구분하여 생성하세요."
INSTRUCTION_TEXT = "다음 검색어와 연관된 키워드를 반드시 '한글'로 변환하여 쉼표(,)로 구분해 생성하세요."


# --- 3. API 서버 시작 시 모델 로드 ---
@app.on_event("startup")
def load_model():
    global model, tokenizer

    # 로컬 테스트용
    save_dir = "./model"
    gguf_filename = "qwen-relkey-q4.gguf"

    # MinIO 사용 시
    # # K8s 내부 MinIO 설정 (기존과 동일)
    # s3 = boto3.client(
    #     's3',
    #     endpoint_url="http://minio-service.autocomplete.svc.cluster.local:9000",
    #     aws_access_key_id='minioadmin',
    #     aws_secret_access_key='minioadmin',
    #     region_name='us-east-1'
    # )
    #
    # bucket_name = "autocomplete"
    # dir_prefix = "qwen_model/" # MinIO 내 Qwen 모델 폴더
    # save_dir = "./downloaded_qwen_model"
    # os.makedirs(save_dir, exist_ok=True)
    #
    # logger.info("--- 📥 MinIO에서 Qwen 모델 다운로드 시작... ---")
    # try:
    #     response = s3.list_objects_v2(Bucket=bucket_name, Prefix=dir_prefix)
    #     if 'Contents' in response:
    #         for obj in response["Contents"]:
    #             file_key = obj["Key"]
    #             if file_key.endswith('/'): continue
    #
    #             file_name = os.path.basename(file_key)
    #             local_file_path = os.path.join(save_dir, file_name)
    #
    #             # 이미 있으면 스킵 (개발 속도 향상)
    #             if not os.path.exists(local_file_path):
    #                 logger.info(f"Downloading: {file_key}")
    #                 s3.download_file(bucket_name, file_key, local_file_path)
    #     else:
    #         logger.warning(f"⚠️ MinIO 버킷({bucket_name}/{dir_prefix})이 비어있습니다.")
    # except Exception as e:
    #     logger.error(f"❌ MinIO Error: {e}")
    #     # 로컬 테스트 시에는 에러 무시하거나 경로 변경 필요
    #
    # logger.info("--- ✅ 다운로드 완료. 모델 로딩 시작... ---")

    try:
        # # Qwen 모델 로드
        # tokenizer = AutoTokenizer.from_pretrained(save_dir, trust_remote_code=True)
        # model = AutoModelForCausalLM.from_pretrained(
        #     save_dir,
        #     device_map="auto",      # CPU/GPU 자동 할당
        #     torch_dtype=torch.float16, # 메모리 최적화
        #     trust_remote_code=True
        # )
        # gguf model load
        model = Llama(
            model_path=f"{save_dir}/{gguf_filename}",
            n_ctx=256,        # 문맥 길이 (입력+출력)
            n_threads=4,      # CPU 코어 사용 개수 (K8s Limit에 맞춤)
            n_gpu_layers=0,   # CPU 전용 (GPU 있다면 -1 또는 레이어 수 지정)
            verbose=False     # 로그 끄기 (성능 향상)
        )
    except Exception as e:
        logger.error(f"❌ 모델 로드 실패: {e}")
        raise e

    logger.info(f"--- Qwen 모델 로딩 완료 ---")


# --- 4. 연관 검색어 생성 로직 ---
# 🌟 [추가] 중복 제거를 위한 정규화 함수
def normalize_text(text: str) -> str:
    """
    대소문자 통일, 공백 및 특수문자 제거 (비교용)
    예: "Pop-Mart" -> "popmart", "POP MART" -> "popmart"
    """
    # 소문자 변환
    text = text.lower()
    # 특수문자 및 공백 제거 (알파벳, 한글, 숫자만 남김)
    text = re.sub(r'[^a-z0-9가-힣]', '', text)
    return text


# --- 4. 연관 검색어 생성 로직 ---
def generate_keywords(query: str, num_results: int = 10) -> List[str]:
    global model

    prompt = (
        f"### Instruction:\n{INSTRUCTION_TEXT}\n\n"
        f"### Input:\n{query}\n\n"
        f"### Response:\n"
    )

    try:
        # 🌟 Llama-cpp 추론 실행
        output = model(
            prompt,
            max_tokens=64,       # 생성 길이 제한 (짧게)
            stop=["<|endoftext|>", "###", "\n"], # 멈춤 조건 (필수!)
            echo=False,          # 프롬프트 제외하고 결과만 받음
            temperature=0.1,     # 낮은 온도로 고정된 결과 유도 (Deterministic)
            top_p=0.9,
            repeat_penalty=1.2   # 반복 방지
        )

        # 결과 텍스트 추출
        generated_text = output['choices'][0]['text'].strip()

        raw_keywords = [k.strip() for k in generated_text.split(',') if k.strip()]

        final_keywords = []
        seen = set()
        seen.add(normalize_text(query))  # 자기 자신 제외

        for k in raw_keywords:
            if len(k) < 2: continue
            norm = normalize_text(k)
            if not norm or norm in seen: continue
            seen.add(norm)
            final_keywords.append(k)

        return final_keywords[:num_results]

    except Exception as e:
        logger.error(f"Inference Error: {e}")
        return []


# --- 5. API 엔드포인트 ---
@app.get("/api/v1/related/search", response_model=RelkeyResponse)
async def get_related(
        q: str = Query(..., title="Query", min_length=1),
        n: int = Query(5, title="Number of keywords")
):
    """
    Qwen 모델을 사용하여 연관 검색어를 생성합니다.
    """
    keywords = generate_keywords(q, num_results=n)

    return {
        "q": q,
        "p": 0.0,
        "subkeys": keywords
    }


@app.get("/api/v1/related")
def read_root():
    return {"message": "Qwen Related Query API is Ready"}
