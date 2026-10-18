import json
import os

import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

cache_file = os.path.join(os.path.dirname(__file__), "data", "cache", "vector_store.json")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # OpenRouter API 키
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")  # OpenRouter Base URL

OPENROUTER_BASE_MODEL = os.getenv("OPENROUTER_BASE_MODEL")  # OpenRouter Base Model
OPENROUTER_EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL")  # OpenRouter Embedding Model


# ✨ 텍스트 로드 함수
def load_text(file_name: str = "enzo_saga.txt") -> str:
    file_path = os.path.join(os.path.dirname(__file__), "data", file_name)
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


# ✨ 캐시 로드 함수
def load_cache(cache_file: str):
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ✨ 캐시 저장 함수
def save_and_create_cache(chunks, vectors) -> bool:
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)

        cache = {
            "chunks": chunks,
            "vectors": vectors
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=4)
        return True
    except (OSError, TypeError, ValueError) as e:
        print(f"캐시 저장 실패: {e}")
        return False


CHUNKERS = {
    "fixed":     lambda t: chunk_fixed(t, size=100),
    "overlap":   lambda t: chunk_overlap(t, size=100, overlap=20),
    "separator": lambda t: chunk_by_separator(t, sep="\n\n"),
}


# ✨ 캐시 확인 후 없으면 임베딩하고 저장
def load_or_create_vector_store(text: str, method: str = "overlap") -> tuple:
    cache = load_cache(cache_file)
    if cache is not None:
        chunks = cache["chunks"]
        vectors = cache["vectors"]
        return chunks, vectors
    
    print("캐시 없음, 임베딩 시작")
    chunks = CHUNKERS[method](text)  # 선택한 청킹 방식 사용

    vectors = post_embedding(input_text=chunks)
    if not chunks or not vectors:
        print("임베딩 실패")
        return None, None

    # 캐시에 저장
    flag = save_and_create_cache(chunks, vectors)
    if not flag:
        print("캐시 생성에 실패했습니다.")
        return None, None

    return chunks, vectors


# ✨ OpenRouter Embedding API 호출 함수
def post_embedding(input_text: str | list[str]) -> list[list[float]]:
    resp = requests.post(
        url=f"{OPENROUTER_BASE_URL}/embeddings",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_EMBEDDING_MODEL,
            "input": input_text,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        print("요청 실패", resp.status_code, resp.text)
        return []

    data = resp.json()
    items = sorted(data.get("data", []), key=lambda d: d["index"])
    return [d["embedding"] for d in items]


# ✨ OpenRouter Chat API 호출 함수
def post_chat(messages: list[dict[str, str]], tools: list[dict[str, str]] | None = None) -> dict:    
    json_data = {
        "model": OPENROUTER_BASE_MODEL,
        "messages": messages,
    }

    # tools가 있을 때만 json_data에 추가
    if tools:
        json_data["tools"] = tools

    resp = requests.post(
        url=f"{OPENROUTER_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json=json_data,
        timeout=30,
    )

    if resp.status_code != 200:
        print("요청 실패", resp.status_code, resp.text)
        return {}

    return resp.json()


# ✨ cosine 유사도 계산
# a: 임베딩된 문장의 vector
# b: 비교할 문장(유저가 프롬프트에 입력한 문장)의 실시간 벡터
def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


# ✨ 고정 길이 청킹
def chunk_fixed(text: str, size: int) -> list[str]:
    if size <= 0:
        raise ValueError("청크 크기는 0보다 커야합니다.")
    return [text[i : i + size] for i in range(0, len(text), size)]


# ✨ 겹침 청킹
def chunk_overlap(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0:
        raise ValueError("청크 크기는 0보다 커야합니다.")

    if overlap < 0 or overlap >= size:
        raise ValueError("overlap은 0 이상 size 미만이어야 합니다.")

    # 청크를 생성하면서 overlap(겹침) 적용
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += size - overlap
    return chunks


# ✨ 구분자 기준 청킹
def chunk_by_separator(text: str, sep: str = "\n\n") -> list[str]:
    if not text:
        return []
    return [part.strip() for part in text.split(sep) if part.strip()]


# ✨ 검색 함수 — 질문과 가장 비슷한 청크 top_k개를 (점수, 청크)로 반환
def search(
    question: str,
    chunks: list[str],
    vectors: list[list[float]],
    top_k: int = 5,
    min_score: float = 0.0,
) -> list[tuple[float, str]]:
    # 1. 질문 임베딩 — 실패하면 빈 결과
    result = post_embedding(input_text=[question])
    if not result:
        return []
    question_vector = np.array(result[0])  # (차원,) 1차원 벡터

    # 2. 모든 청크 벡터와의 코사인 유사도를 한 번에 계산
    vectors = np.array(vectors)  # (청크 수, 차원)
    similarity = (vectors @ question_vector) / (
        np.linalg.norm(vectors, axis=1) * np.linalg.norm(question_vector)
    )  # (청크 수,) — 청크마다 점수 하나

    # 3. 점수 높은 순으로 상위 top_k 인덱스
    top_indices = np.argsort(similarity)[::-1][:top_k]

    # 4. (점수, 청크)로 묶으면서 min_score 미만은 버림
    return [
        (float(similarity[i]), chunks[i])
        for i in top_indices
        if similarity[i] >= min_score
    ]
