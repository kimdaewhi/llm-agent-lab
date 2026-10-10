# ============================================================
# 🧬 01_embedding.py — 문장을 벡터로, 의미를 거리로
# ============================================================
#
# RAG의 검색은 "질문과 비슷한 문서 조각"을 찾는 일이다.
# 그 "비슷함"을 컴퓨터가 계산할 수 있게 만드는 게 임베딩.
# 청킹·벡터 스토어로 가기 전에, 벡터 하나와 유사도 계산부터 직접 만져본다.
#
# 🎯 목적
#   - 임베딩 API를 직접 호출해 응답 구조와 벡터의 모양 확인
#   - 코사인 유사도를 라이브러리 없이 직접 구현
#   - 임베딩이 단어 겹침이 아니라 의미를 잡는지 확인
#
# 🔧 방법
#   - POST {BASE_URL}/embeddings 로 문장 하나를 임베딩
#     · 모델명은 EMBEDDING_MODEL 환경변수로 분리
#     · 응답 전문 출력 → data[0].embedding 길이(차원), usage 확인
#   - cosine_similarity(a, b) 직접 구현 (내적 / 각 벡터 크기의 곱)
#   - 기준 문장 하나에 대해 아래 문장들과 유사도 비교
#     · 뜻 같음 + 단어 다름   (예: "환불 받고 싶어요" ↔ "돈 돌려주세요")
#     · 단어 겹침 + 뜻 다름   (예: "배가 아프다" ↔ "배가 항구에 들어왔다")
#     · 같은 뜻의 영어 번역
#     · 전혀 무관한 문장
#   - input에 문장 리스트를 한 번에 넘겨 배치 임베딩도 시도
#
# 🔍 관찰
#   - 벡터 차원 수, 값의 범위, 벡터 크기(norm)가 1인지 (정규화 여부)
#   - 유사도 순위가 직관과 맞는지 — 특히 단어 겹침 vs 뜻 같음
#   - 무관한 문장의 유사도가 0 근처인지, 생각보다 높은지
#   - 한국어 ↔ 영어 번역 쌍의 유사도
#   - 같은 문장을 두 번 임베딩하면 벡터가 완전히 같은지
#   - 배치 요청과 개별 요청의 결과·토큰 차이
#   - 임베딩 모델 비용 vs 채팅 모델 비용
#
# ✅ 결론 (openai/text-embedding-3-small 기준)
#   - 질문도 문장과 같은 임베딩 모델로 벡터화해야 비교가 된다. chat은 01에서 쓰지 않는다.
#     문서는 시작할 때 한 번, 질문은 매번. 같은 함수를 쓰고 역할만 다르다.
#   - 같은 문장도 1.0이 아니라 0.9999. 같은 입력이어도 벡터가 미세하게 다르다.
#   - 바닥값은 생각보다 낮다. 무관한 질문의 최고점이 0.15, 음수(-0.004)도 나온다.
#     → 점수는 절대값이 아니라 바닥값과의 거리로 읽는다.
#   - 고유명사가 순위를 끌고 간다.
#     · 기준 문장 질문 → "음바페 득점왕"(0.52)이 같은 사건의 번역문(0.49)보다 위
#     · 이름 없는 같은 사건 문장은 0.34로 중위권
#     · 반대로 이름 없는 질문("이적료 없이 팀을 옮긴 선수는?")에선 그 문장이 1위(0.41)
#   - 언어 장벽이 크다. 같은 사건이어도 질문과 같은 언어의 문장이 압도적으로 유리.
#     · "Mbappé Real Madrid" → 영어 문장 0.65, 한국어 원문 0.36
#     · "음바페 이적" → 영어 문장 0.095로 꼴찌
#   - 숫자의 크기는 모른다. "역대급으로 비싼 이적"에 1억·2억 유로 문장을 못 찾고 전부 바닥 근처.
#   - 짧은 질문은 점수가 전부 낮고 순위가 노이즈다.
#     "맨유"(1위 0.19), "주식이 떨어졌다"(맨유 주가 문장이 2위) — 1위가 바닥과 붙어 있으면 믿지 않는다.
#   - 구조가 같은 다른 분야는 2위권에 붙는다. "경쟁사로 옮겼다" → 개발자 0.45, 축구 이적 0.24
#   - 임베딩은 문장 전체를 점 하나로 섞는다. 질문의 초점을 모르고, 같은 맥락에 자주 나온 표현을 가깝게 둘 뿐.
#     음바페 ↔ Mbappé 연결도 사전이 아니라 학습 통계로 생긴다.
#   - RAG로 가져갈 것
#     · 1위 점수가 0.25 미만이면 "관련 문서 없음" 처리 (04의 "모른다" 기준)
#     · 짧은 키워드 질문은 문장형으로 재작성, 숫자·고유명사는 키워드 검색과 섞기
#     · 문서·질문 언어를 맞추거나 다국어 모델 사용
# ============================================================
import os

import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL")

SENTENCES_PATH = os.path.join(os.path.dirname(__file__), "data", "sentences.txt")


# 임베딩 요청 함수 — 문자열 하나든 리스트든 항상 벡터 리스트로 반환
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
    )

    if resp.status_code != 200:
        print("요청 실패:", resp.status_code, resp.text)
        return []

    data = resp.json()
    items = sorted(data["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in items]


# 문장 파일 읽기 — 한 줄에 한 문장, 빈 줄은 건너뜀
def load_sentences(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


# cosine 유사도 계산
# a: 임베딩된 문장의 vector
# b: 비교할 문장(유저가 프롬프트에 입력한 문장)의 실시간 벡터
def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


if __name__ == "__main__":
    # 문장 임베딩 — 시작할 때 한 번만
    sentences = load_sentences(SENTENCES_PATH)
    sentence_vectors = post_embedding(sentences)
    if not sentence_vectors:
        print("문장 임베딩 실패. 종료합니다.")
        raise SystemExit(1)

    print(
        f"문장 {len(sentence_vectors)}개 임베딩 완료 (차원: {len(sentence_vectors[0])})"
    )
    print("종료하려면 'exit', 콘솔을 비우려면 'clear'를 입력하세요.")

    while True:
        # 질문
        question = input("\n질문을 입력하세요: ")

        # 종료
        if question.strip().lower() == "exit":
            print("프로그램을 종료합니다.")
            break

        # 콘솔 클리어
        if question.strip().lower() == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue

        # 질문 임베딩 — 문장과 같은 임베딩 모델로
        result = post_embedding(question)
        if not result:
            continue
        q_vec = result[0]

        # TODO: cosine_similarity(q_vec, 각 문장 벡터) 계산 → 점수순 정렬 → 전체 출력
        similarities = [
            (sent, cosine_similarity(q_vec, vec))
            for sent, vec in zip(sentences, sentence_vectors)
        ]
        similarities.sort(key=lambda x: x[1], reverse=True)
        for sent, score in similarities:
            print(f"유사도: {score:.4f} | 문장: {sent}")
