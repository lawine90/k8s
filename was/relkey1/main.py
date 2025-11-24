import re
import os
import math
import boto3
import torch
import logging
from typing import List, Tuple

from fastapi import FastAPI, Query
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

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
        # Qwen 모델 로드
        tokenizer = AutoTokenizer.from_pretrained(save_dir, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            save_dir,
            device_map="auto",      # CPU/GPU 자동 할당
            torch_dtype=torch.float16, # 메모리 최적화
            trust_remote_code=True
        )
    except Exception as e:
        logger.error(f"❌ 모델 로드 실패: {e}")
        raise e

    logger.info(f"--- Qwen 모델 로딩 완료 (Device: {model.device}) ---")


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
def generate_keywords(query: str, num_results: int = 10) -> Tuple[float, List[str]]:
    global model, tokenizer

    prompt = (
        f"### Instruction:\n{INSTRUCTION_TEXT}\n\n"
        f"### Input:\n{query}\n\n"
        f"### Response:\n"
    )

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
            num_beams=3,
            early_stopping=True,
            repetition_penalty=1.2,
            eos_token_id=tokenizer.eos_token_id,
            return_dict_in_generate=True,
            output_scores=True
        )

    sequence_prob = 0.0
    if hasattr(outputs, 'sequences_scores'):
        # Log Probability의 합이므로 exp를 취하면 확률이 됩니다.
        # 값이 매우 작을 수 있으므로 상황에 따라 정규화가 필요할 수 있습니다.
        sequence_prob = math.exp(outputs.sequences_scores[0].item())

    output_sequence = outputs.sequences[0]
    full_text = tokenizer.decode(output_sequence, skip_special_tokens=True)

    try:
        if "### Response:\n" in full_text:
            generated_text = full_text.split("### Response:\n")[1].strip()
        else:
            generated_text = full_text

        # 1차 분리
        raw_keywords = [k.strip() for k in generated_text.split(',') if k.strip()]

        # 🌟 [수정] 중복 및 유사 변형 필터링 로직
        final_keywords = []
        seen_normalized = set()

        # 입력 쿼리도 정규화해서 제외 목록에 추가 (자기 자신 추천 방지)
        query_normalized = normalize_text(query)
        seen_normalized.add(query_normalized)

        for k in raw_keywords:
            # 1. 너무 짧은 단어 제외 (1글자)
            if len(k) < 2:
                continue

            # 2. 정규화 후 중복 검사
            norm_k = normalize_text(k)

            if not norm_k: # 정규화했더니 빈 문자열이면 제외
                continue

            if norm_k in seen_normalized:
                continue

            # 3. 포함 관계 필터링 (선택 사항: "팝마트"가 있는데 "팝마트 코리아"가 나오면 허용할지 말지)
            # 여기서는 단순히 '정확히 같은 변형'만 막습니다.

            seen_normalized.add(norm_k)
            final_keywords.append(k)

        return sequence_prob, final_keywords[:num_results]

    except Exception as e:
        logger.warning(f"파싱 에러: {e}")
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
    prob, keywords = generate_keywords(q, num_results=n)

    return {
        "q": q,
        "p": prob,
        "subkeys": keywords
    }


@app.get("/api/v1/related")
def read_root():
    return {"message": "Qwen Related Query API is Ready"}
