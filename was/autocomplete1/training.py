import os
from transformers import (
    Trainer,
    TrainingArguments,
    AutoConfig,
    AutoModelForCausalLM,
    PreTrainedTokenizerFast,
    DataCollatorForLanguageModeling,
)
from datasets import load_dataset


# -- 0. functions
def tokenize_function(examples):
    return tokenizer(examples["text"])


def chunking(examples):
    # concat all keywords
    concatenated_examples = {k: sum(examples[k], []) for k in examples.keys()}
    total_length = len(concatenated_examples[list(examples.keys())[0]])

    # remove over size keywords
    total_length = (total_length // BLOCK_SIZE) * BLOCK_SIZE

    # split concated keywords by BLOCK_SIZE
    result = {
        k: [t[i : i + BLOCK_SIZE] for i in range(0, total_length, BLOCK_SIZE)]
        for k, t in concatenated_examples.items()
    }

    # 'labels' == 'input_ids' in Causal LM task
    result["labels"] = result["input_ids"].copy()
    return result


# -- 1. configs
BLOCK_SIZE = 32     # autocomplete를 위한 fine-tunning이라 사이즈를 작게
BASE_MODEL = "skt/kogpt2-base-v2"
GDRIVE_PATH = "/content/drive/MyDrive/autocomplete"
DATA_FILE = f"{GDRIVE_PATH}/data/keywords.txt"
TOKENIZER_FILE = f"{GDRIVE_PATH}/data/bpe-tokenizer.json"
OUTPUT_DIR = f"{GDRIVE_PATH}/model1"

print(f"Tokenize file: {TOKENIZER_FILE}")
print(f"Data file: {DATA_FILE}")
print(f"Output Dir: {OUTPUT_DIR}")


# -- 2. import tokenizer & keywords
tokenizer = PreTrainedTokenizerFast(
    tokenizer_file=TOKENIZER_FILE,
    bos_token="[BOS]",      # Begin-Of-Sentence
    eos_token="[EOS]",      # End-Of-Sentence
    unk_token="[UNK]",
    pad_token="[PAD]",      # Padding
    mask_token="[MASK]"
)
print(f"토크나이저 로드 완료. Vocab size: {tokenizer.vocab_size}")

raw_datasets = load_dataset("text", data_files=DATA_FILE, split="train")
tokenized_datasets = raw_datasets.map(
    tokenize_function,
    batched=True,
    num_proc=4,                 # 4개의 CPU 코어를 사용하여 병렬 처리
    remove_columns=["text"]     # 토큰화 후 원본 텍스트 컬럼 삭제
)
print(f"원본 데이터 사이즈: {raw_datasets.dataset_size}")

# chunking
lm_datasets = tokenized_datasets.map(
    chunking,
    batched=True,
    num_proc=4,
)
print(f"데이터 전처리 완료. 총 {len(lm_datasets)}개의 학습 샘플 생성.")


# -- 3. training config
config = AutoConfig.from_pretrained(BASE_MODEL)
model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, config=config)

# resize model's embedding size then set padding token id
model.resize_token_embeddings(len(tokenizer))
model.config.pad_token_id = tokenizer.pad_token_id
print(f"모델 임베딩 크기: {model.get_input_embeddings().weight.shape[0]}")

# data_collator for Causal LM
# mlm=False means Causal LM
data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False
)

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,            # 모델이 저장될 디렉토리
    overwrite_output_dir=True,        # 덮어쓰기 허용
    num_train_epochs=7,               # 테스트용은 1
    per_device_train_batch_size=16,   # 테스트용은 2
    gradient_accumulation_steps=4,
    save_steps=1000,                  # 10,00 스텝마다 모델 체크포인트 저장
    save_total_limit=1,               # 최대 1개의 체크포인트만 유지
    logging_steps=500,                # 500 스텝마다 학습 로그 출력

    fp16=True,                        # GPU option
    no_cuda=False,                    # GPU option

    report_to="none",                 # "wandb"나 "tensorboard" 로깅 비활성화
)

trainer = Trainer(
    model=model,
    args=training_args,
    data_collator=data_collator,
    train_dataset=lm_datasets,
    # eval_dataset=lm_datasets_validation,
)

# -- 3. training
trainer.train()
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"학습 완료! 최종 모델이 '{OUTPUT_DIR}' 경로에 저장되었습니다.")