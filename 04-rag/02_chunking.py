# ============================================================
# ✂️ 02_chunking.py — 긴 문서를 어디서 자를 것인가
# ============================================================
#
# 01은 한 줄이 곧 검색 단위였다. 실제 문서는 길어서 통째로 임베딩하면
# 모든 내용이 점 하나로 섞이고, 너무 잘게 자르면 짧은 텍스트라 점수가 낮고 노이즈가 된다.
# 같은 문서를 세 가지 방식으로 잘라, 경계가 검색 결과를 어떻게 바꾸는지 본다.
#
# 🎯 목적
#   - 고정 길이 / 고정 길이 + overlap / 문단(구분자) 기준 청킹을 직접 구현
#   - 각 방식이 문장·문단 경계를 어디서 끊는지 눈으로 확인
#   - 같은 질문에 대해 청킹 방식별 검색 순위·점수가 어떻게 달라지는지 비교
#
# 🔧 방법
#   - 문서: data/enzo_saga.txt (2026 여름 엔조·카마라·발로건·리라 연쇄 이적 사가, 문단 12개)
#     · 임베딩 모델이 학습하지 못한 최신 사건 → 문서에서 찾아야만 답할 수 있음
#     · 문단 길이가 들쭉날쭉함 (긴 문단 ~320자, 한 줄 문단 16자, 목록 문단)
#     · "그는", "그를", "딜은"처럼 가리키는 대상이 앞 문장·앞 문단에 있는 문장이 많음
#     · 금액이 여러 딜에 흩어져 있음 (1억 700만 / 1억 2,000만 / 1억 2,500만 파운드, 5,500만 / 7,000만 유로)
#   - 청킹 함수 3개 (입력 str → 출력 list[str])
#     · chunk_fixed(text, size)               : size 글자마다 자름
#     · chunk_overlap(text, size, overlap)    : 앞 청크 끝 overlap 글자를 다음 청크 앞에 겹침
#     · chunk_by_separator(text, sep="\n\n")  : 문단 단위로 자름
#   - 01의 post_embedding / cosine_similarity를 가져와 그대로 사용
#   - 방식별로 청크를 배치 임베딩 (방식당 요청 1번), 청크 수 출력
#   - 질문 하나를 한 번만 임베딩해 세 방식에 같이 쓰고, 방식별 top-3 출력
#     · print_top_chunks: 점수 + 글자 수 + 청크 전문 (줄바꿈은 ⏎로 표시해 경계가 보이게)
#   - size 100 / overlap 20, size 200 / overlap 50 두 설정으로 실행
#   - 같은 질문 목록을 세 방식에 똑같이 입력
#     · 이름과 숫자가 다른 문장에 있는 질문     (예: "카마라 이적료는 얼마로 합의됐어?")
#     · 비슷한 숫자가 여럿인 질문               (예: "엔조가 맨시티로 갈 때 이적료는?")
#     · 답이 여러 문단에 걸친 질문 (multi-hop)  (예: "모나코는 왜 카마라 딜을 깼어?")
#     · 짧은 문단 + 목록 문단에 답이 있는 질문  (예: "발로건은 왜 에버턴 이적을 거부했어?")
#     · 문단 하나 안에서 답이 끝나는 질문       (예: "리라 영입은 왜 무산됐어?")
#     · 문서와 무관한 질문 (바닥값 확인용)
#
# 🔍 관찰
#   - 고정 길이가 문장·단어 중간을 자르는 위치, 그 청크의 점수
#   - overlap이 경계에 걸린 답을 살리는지, 같은 내용이 top-3에 중복으로 뜨는지
#   - 문단 기준에서 여러 사건이 섞인 긴 문단은 점수가 희석되는지, 한 줄 문단은 노이즈인지
#   - "그는", "딜은"으로 시작하는 청크 — 01의 고유명사 편향대로 이름이 빠지면 순위가 밀리는지
#   - 엔조 이적료 질문에 다른 딜의 금액 청크(카마라 5,500만, 첼시 영입가 1억 700만)가 섞이는지
#   - multi-hop 질문은 어떤 방식이든 top-1 청크 하나로는 답이 안 되는지 → 03의 top-k가 필요한 이유
#   - 같은 질문의 1위 점수가 방식마다 얼마나 다른지, 01의 바닥값(~0.15)·컷오프(0.25)와 비교
#   - size / overlap 값을 바꿨을 때 결과가 얼마나 흔들리는지
#   - 청크 수가 늘어난 만큼 임베딩 토큰(usage)도 늘어나는지 — overlap의 비용
#
# ✅ 결론 (openai/text-embedding-3-small, enzo_saga.txt 2,172자 기준)
#   - 정답인 청킹 방식은 없다. 세 방식은 실패하는 지점이 서로 다르다.
#     · 고정 길이 : 아무 데서나 자른다. 이름·숫자가 쪼개진다 ("엔|조", "1억|700만").
#                   대신 짧은 문단을 이웃 문단과 합쳐 줘서, 짧은 문단이 노이즈가 되는 걸 우연히 막는다.
#     · overlap   : 경계에 걸린 정보를 일부 살린다. size 100에서 "엔조"가 잘리지 않았다.
#                   하지만 다 살리진 못한다. overlap 50에서도 "1억"이 앞 청크로 넘어갔다.
#                   겹친 청크끼리 top-3 자리를 나눠 먹는다.
#     · 구분자    : 의미 단위가 보존돼 답이 깔끔하고 multi-hop에 강하다.
#                   "모나코는 왜 카마라 딜을 깼어?"에 필요한 문단 3개가 top-3에 다 들어왔다.
#                   대신 결과가 글쓴이의 문단 나누기에 달려 있다. 긴 문단은 점수가 묽어진다.
#   - 점수와 유용성은 별개다.
#     · "발로건 메디컬에 무슨 문제가 있었어?" → 16자 문단 "문제는 발로건의 메디컬이었다."가 0.7365로 1위.
#       실험 전체 최고점인데 담긴 정보는 없다. 질문을 바꿔 말한 문장일 뿐이다.
#     · 제목 줄도 같다. "엔조 이적료는 얼마야?"에 세 방식 모두 제목(40자)이 1위.
#     → 너무 짧은 청크는 합치거나 버린다. 제목은 본문 청크에 붙이는 편이 낫다.
#   - 정답 청크를 찾아도 정답이 잘려 있을 수 있다.
#     · "협상을 중단시킨 사람은?" → overlap 1위가 정답 문장인데 '루 단장은…'으로 시작. 정답인 이름 "스쿠루"가 빠졌다.
#     · 점수만 보면 성공이라 더 위험하다.
#   - 이름과 숫자가 다른 문장에 있으면 못 찾는다.
#     · "카마라 이적료는 얼마로 합의됐어?" → 금액 문장에 "카마라"가 없어 고정 길이·overlap은 top-3 밖.
#       "카마라"라는 이름이 들어간 다른 청크들이 위를 차지했다. 01의 고유명사 편향 그대로.
#   - 청킹으로는 못 고치는 실패가 있다.
#     · "첼시가 열받은 이유는?" → 세 방식 모두 top-3에 정답("크게 분노") 없음. "첼시"가 많은 문단이 이겼다.
#     · "왜"를 묻는 질문은 이유가 아니라 등장인물을 찾는다. 질문의 초점을 모르는 임베딩의 한계다.
#   - 01의 컷오프 0.25를 그대로 쓸 수 없다. 바닥값이 청크 크기에 따라 달라진다.
#     · "리라 영입은 왜 무산됐어?" → 구분자 방식은 정답이 1위인데 0.249
#     · "오늘 점심 뭐 먹지?" → overlap(100자)의 바닥값이 0.22까지 올라감
#   - 비용은 문서 쪽에 몰려 있다. 시작할 때 청크 임베딩은 느리지만, 이후 질문은 빠르다.
#     · 질문마다 드는 건 질문 임베딩 요청 1번 + 로컬 코사인 계산뿐. 청크 수십 개는 계산이 순식간이다.
#     · 대신 실행할 때마다 청크를 다시 임베딩한다 → 03에서 벡터 캐시로 해결
#   - 그래서 실무에서는 섞는다 (recursive 청킹)
#     · 구분자로 먼저 자르고 → 너무 짧은 조각은 이웃과 합치고 → 너무 긴 조각은 문장 단위로 다시 나누고 → 경계에 약간의 overlap
#     · 그래도 남는 실패(고유명사 편향, multi-hop)는 03의 top-k, 키워드 검색 섞기, 04의 답변 생성에서 다룬다
# ============================================================
import os
import textwrap

import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL")


# 📄 텍스트 로드 함수
def load_text() -> str:
    file_path = os.path.join(os.path.dirname(__file__), "data", "enzo_saga.txt")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


# 🧱 고정 길이 청킹
def chunk_fixed(text: str, size: int) -> list[str]:
    if size <= 0:
        raise ValueError("청크 크기는 0보다 커야합니다.")
    return [text[i : i + size] for i in range(0, len(text), size)]


# 🔁 겹침 청킹
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


# 📑 구분자 기준 청킹
def chunk_by_separator(text: str, sep: str = "\n\n") -> list[str]:
    if not text:
        return []
    return [part.strip() for part in text.split(sep) if part.strip()]


# 🧬 임베딩 요청 함수
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


# 📐 cosine 유사도 계산
# a: 임베딩된 문장의 vector
# b: 비교할 문장(유저가 프롬프트에 입력한 문장)의 실시간 벡터
def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


# 👁️공통 출력 함수 정의
def print_top_chunks(title, chunks, embeddings, q_vec, top_k=3):
    similarities = [
        (chunk, cosine_similarity(q_vec, emb)) for chunk, emb in zip(chunks, embeddings)
    ]
    similarities.sort(key=lambda x: x[1], reverse=True)

    print(f"\n━━━ {title} ━━━")
    for rank, (chunk, score) in enumerate(similarities[:top_k], start=1):
        print(f"\n  {rank}위 | 유사도 {score:.4f} | {len(chunk)}자")
        # 줄바꿈은 ⏎로 표시 — 청크가 문단 경계를 넘는지 보이게
        flat = chunk.replace("\n", "⏎")
        for line in textwrap.wrap(flat, width=45):
            print(f"      {line}")


if __name__ == "__main__":
    text = load_text()
    chunk_size = 200
    overlap = 50

    # 1-1. 임베딩(고정 청크 방식)
    fixed_chunks = chunk_fixed(text=text, size=chunk_size)  # 예시: 100자 단위로 청킹
    fixed_embeddings = post_embedding(fixed_chunks)
    if not fixed_embeddings:
        print("청크 임베딩 실패. 종료합니다.")
        raise SystemExit(1)
    else:
        print("청크 수:", len(fixed_chunks))
        print("임베딩 수:", len(fixed_embeddings))

    # 1-2. 임베딩(overlap 청크 방식)
    overlap_chunks = chunk_overlap(
        text=text, size=chunk_size, overlap=overlap
    )  # 예시: chunk_size 단위, overlap 겹침
    overlap_embeddings = post_embedding(overlap_chunks)
    if not overlap_embeddings:
        print("overlap 청크 임베딩 실패. 종료합니다.")
        raise SystemExit(1)
    else:
        print("overlap 청크 수:", len(overlap_chunks))
        print("overlap 임베딩 수:", len(overlap_embeddings))

    # 1-3. 임베딩(구분자 기준 청크 방식)
    sep_chunks = chunk_by_separator(text=text, sep="\n\n")
    sep_embeddings = post_embedding(sep_chunks)
    if not sep_embeddings:
        print("구분자 기준 청크 임베딩 실패. 종료합니다.")
        raise SystemExit(1)
    else:
        print("구분자 기준 청크 수:", len(sep_chunks))
        print("구분자 기준 임베딩 수:", len(sep_embeddings))

    # 2. 질문에 대한 임베딩 및 유사도를 계산하여 가장 유사한 청크를 찾기
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

        # 유사도 상위 3개 청크 찾기(각각 고정 청크, overlap 청크, 구분자 기준 청크)
        print_top_chunks(
            "[Fixed Chunks] 상위 3개 유사 청크", fixed_chunks, fixed_embeddings, q_vec
        )
        print_top_chunks(
            "[Overlap Chunks] 상위 3개 유사 청크",
            overlap_chunks,
            overlap_embeddings,
            q_vec,
        )
        print_top_chunks(
            "[Separator Chunks] 상위 3개 유사 청크", sep_chunks, sep_embeddings, q_vec
        )
