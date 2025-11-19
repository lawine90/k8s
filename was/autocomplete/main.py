import os
import boto3
import torch
import pytrie
import logging

from enum import Enum
from functools import lru_cache
from fastapi import FastAPI, Query
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, PreTrainedTokenizerFast
from typing import List, Tuple

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# (Pydantic) API 응답 형식을 정의
class ReturnType(str, Enum):
    FULL = "full"
    token = "token"


class SubkeyResponse(BaseModel):
    subkey: str
    prob: float


class ResultResponse(BaseModel):
    q: str
    subkeys: List[SubkeyResponse]


# --- 1. FastAPI 앱 및 Pydantic 모델 정의 ---
app = FastAPI(title="AI Autocomplete API")

# --- 2. 모델/토크나이저 전역 변수 선언 ---
# API 서버가 시작될 때 딱 한 번만 로드하기 위한 전역 변수
model = None
tokenizer = None
vocab = {}
choseong_to_ids_map = {}
syllable_trie = None
BPE_SPACE = " "  # Hugging Face 토크나이저의 특수 공백 문자 (U+2581)

# --- 3. 한글 초성(Jamo) 분리 헬퍼 ---
CHOSEONG_LIST = [
    'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ',
    'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
]
CHOSEONG_SET = set(CHOSEONG_LIST)


def get_choseong(char):
    if '가' <= char <= '힣':
        choseong_index = (ord(char) - ord('가')) // (21 * 28)
        return CHOSEONG_LIST[choseong_index]
    elif char in CHOSEONG_SET:
        return char
    else:
        return None


# def quantize_model(model_instance, device):
#     """CPU 추론 속도를 높이기 위해 모델을 8-bit로 양자화"""
#     if device == "cpu":
#         try:
#             # torch.quantization.quantize_dynamic을 사용하여
#             # 모델의 Linear 레이어들을 int8로 변환
#             model_quantized = torch.quantization.quantize_dynamic(
#                 model_instance, {torch.nn.Linear}, dtype=torch.qint8
#             )
#             print("--- 🧠 (최적화) CPU 모델 동적 양자화(int8) 적용 완료 ---")
#             return model_quantized
#         except Exception as e:
#             print(f"--- ⚠️ (경고) 모델 양자화 실패: {e} ---")
#             return model_instance
#     return model_instance


# --- 4. API 서버 시작 시 모델 로드 ---
@app.on_event("startup")
def load_model_and_vocab():
    """
    FastAPI 서버가 시작될 때, 모델과 어휘집을 전역 변수(RAM)에 로드
    """
    global model, tokenizer, vocab, choseong_to_ids_map, syllable_trie

    # # 로컬 테스트용
    # save_dir = "./model"
    # print(f"--- AI 모델 로딩 시작: {save_dir} ---")

    s3 = boto3.client(
        's3',
        endpoint_url="http://minio-service.autocomplete.svc.cluster.local:9000",
        aws_access_key_id='minioadmin',
        aws_secret_access_key='minioadmin',
        region_name='us-east-1'
    )
    bucket_name = "autocomplete"
    dir_prefix = "model/"
    save_dir = "./downloaded_model"
    os.makedirs(save_dir, exist_ok=True)

    print("--- 📥 MinIO에서 모델 다운로드 시작... ---")
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=dir_prefix)
        if 'Contents' in response:
            for obj in response["Contents"]:
                file_key = obj["Key"]
                if file_key.endswith('/'):
                    continue
                local_file_path = os.path.join(save_dir, os.path.basename(file_key))

                logger.info(f"Downloading: {file_key}")
                s3.download_file(bucket_name, file_key, local_file_path)
        else:
            logger.warning("⚠️ MinIO 버킷이 비어있습니다.")
    except Exception as e:
        logger.error(f"MinIO Error: {e}")
    print("--- ✅ 다운로드 완료. 모델 로딩 시작... ---")

    tokenizer = PreTrainedTokenizerFast.from_pretrained(save_dir)
    model = AutoModelForCausalLM.from_pretrained(save_dir)

    # GPU or CPU
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # # quantize model
    # model = quantize_model(model_32, device)

    model.to(device)
    model.eval()
    print(f"--- 모델 로딩 완료 ({device}) ---")

    # 어휘집 및 초성 맵 구축
    vocab = tokenizer.get_vocab()
    print(f"--- 어휘집({len(vocab)}개) 분석 및 초성 맵 구축 중... ---")

    # create vocab with trie
    syllable_trie = pytrie.StringTrie()

    for token_text, token_id in vocab.items():
        if token_text.startswith("##"): continue

        clean_token = token_text[1:] if token_text.startswith(BPE_SPACE) else token_text
        if not clean_token: continue

        first_char = clean_token[0]
        choseong = get_choseong(first_char)

        if choseong:
            if choseong not in choseong_to_ids_map:
                choseong_to_ids_map[choseong] = []
            choseong_to_ids_map[choseong].append(token_id)

        if clean_token in syllable_trie:
            syllable_trie[clean_token].append(token_id)
        else:
            syllable_trie[clean_token] = [token_id]

    print(f"--- 초성 맵 & Trie 구축 완료. API 서버 준비 완료 ---")


# --- 5. 자동완성 핵심 로직 ---
@lru_cache(maxsize=2048)
def get_recommendations(
        full_prompt: str,
        num_results: int = 10,
        return_type: str = "full"
) -> List[Tuple[str, float]]:
    """
    input query를 받아서 다음에 나올 토큰을 제안
    """
    global model, tokenizer, vocab, choseong_to_ids_map, syllable_trie

    # (1) Context / Fragment 분리
    last_space_index = full_prompt.rfind(" ")
    if last_space_index == -1:
        context = ""
        fragment = full_prompt
    else:
        context = full_prompt[:last_space_index + 1]
        fragment = full_prompt[last_space_index + 1:]

        # (2-1) 모델 추론
    device = model.device # 모델이 로드된 device (cuda or cpu)
    if not context:
        input_ids_tensor = torch.tensor([[tokenizer.bos_token_id]], device=device)
    else:
        inputs = tokenizer(context, return_tensors="pt").to(device)
        input_ids_tensor = inputs.input_ids

    with torch.no_grad():
        outputs = model(input_ids=input_ids_tensor)

    last_token_logits = outputs.logits[0, -1, :]
    all_probabilities = torch.softmax(last_token_logits, dim=-1) # 확률로 변환

    # (2-2) 컨텍스트 중복 토큰 블랙리스트
    blacklist_ids = set(input_ids_tensor[0].tolist())

    # (3) 어휘집(Whitelist) 필터링
    whitelist_ids = []
    is_jamo_fragment = (len(fragment) == 1 and fragment in CHOSEONG_SET)

    if is_jamo_fragment:
        # 3.1: 초성(e.g. "강남역 ㅁ")일 경우, 미리 만든 '초성 맵' 사용
        if fragment in choseong_to_ids_map:
            for token_id in choseong_to_ids_map[fragment]:
                if token_id in blacklist_ids: continue
                whitelist_ids.append(token_id)
    else:
        # 3.2: 음절(e.g. '강남역 맛')일 경우, 'Trie'로 prefix 검색
        try:
            # "맛"으로 시작하는 모든 토큰 리스트
            # (예: [("맛집", [123, 456]), ("맛있는", [789]), ...])
            matches = syllable_trie.items(prefix=fragment)

            for clean_token, token_id_list in matches:
                # 'fragment'와 정확히 일치하는 토큰은 제외 (v5 로직)
                if clean_token == fragment:
                    continue

                for token_id in token_id_list:
                    if token_id in blacklist_ids: continue
                    whitelist_ids.append(token_id)
        except KeyError:
            pass # Trie에 일치하는 prefix가 없는 경우

    if not whitelist_ids:
        return []

    # (4) 필터링
    mask = torch.ones_like(last_token_logits) * -float("Inf")
    mask[whitelist_ids] = 0.0
    filtered_logits = last_token_logits + mask

    # (5) Top-K 추출
    top_k_indices = torch.topk(filtered_logits, num_results).indices

    # (6) 결과 조합
    recommendations = []
    context_ids = input_ids_tensor[0]

    for token_id in top_k_indices:
        new_token_id_item = token_id.item()
        if last_token_logits[new_token_id_item] == -float("Inf"):
            continue

        probability = all_probabilities[new_token_id_item].item()

        if return_type == "token":
            # 단순히 해당 토큰 ID 하나만 디코딩
            decoded_text = tokenizer.decode([new_token_id_item], skip_special_tokens=True)
            # BPE 토크나이저는 단어 앞에 공백을 붙이는 경우가 많으므로 제거(.strip())
            final_text = decoded_text.strip()
        else:
            new_sequence_ids = torch.cat([context_ids, token_id.unsqueeze(0)], dim=0)
            final_text = tokenizer.decode(new_sequence_ids, skip_special_tokens=True)

        recommendations.append((final_text, probability))

    return recommendations


# --- 6. API 엔드포인트 ---
@app.get("/api/v1/search", response_model=ResultResponse)
async def autocomplete(
        q: str = Query(
            ...,
            min_length=1,
            max_length=25,
            title="Search Query",
            description="자동완성을 요청할 검색어 문자열"
        ),

        n: int = Query(
            default=3,
            title="Number of subkeys",
            description="리턴될 문자열의 개수"
        ),

        return_type: ReturnType = Query(
            default=ReturnType.FULL,
            title="Return Type",
            alias="type",
            description="'full'이면 전체 문장, 'token'이면 마지막 제안되는 단어만 반환"
        )
):
    """
    GPT-2 모델을 기반으로 자동완성 추천 목록을 반환
    """
    # 핵심 로직 함수 호출
    results = get_recommendations(q, num_results=n, return_type=return_type.value)

    # (v7) 결과를 API 응답 형식(JSON)으로 변환
    response_data = {
        "q": q,
        "subkeys": [
            SubkeyResponse(subkey=text, prob=prob)
            for text, prob in results
        ]
    }

    return response_data


# --- (선택) 루트 경로 ---
@app.get("/")
def read_root():
    return {"message": "AI Autocomplete API. ' /docs '로 이동하여 API 문서를 확인하세요."}
