# ============================================================
# 💬 04_generate_answer.py — 검색한 청크를 근거로 LLM이 답하게 하기
# ============================================================
#
# 03에서 "검색 점수만으로는 문서에 답이 있는지 판단할 수 없다"가 나왔다.
# 그래서 역할을 나눈다. 찾기는 search(top-k)가 하고, 답이 있는지 판단 + 답변은 LLM이 한다.
#
# 🎯 목적
#   - 답 있는 질문("엔조 이적료는?")에 청크 근거로 맞게 답하는가
#   - 답 없는 질문("카마라 주급은?")에 지어내지 않고 "문서에 없다"고 하는가
#
# 🔧 방법
#   - ru.load_or_create_vector_store(text, method)로 chunks, vectors를 불러온다
#     · method("fixed" / "overlap" / "separator")가 청킹 방식과 캐시 파일 이름을 같이 정한다
#   - ru.search(question, chunks, vectors, top_k=5)로 청크 top-5 (점수는 빼고 텍스트만 LLM에 전달)
#   - 청크를 번호 붙여 하나의 문자열로 묶어 프롬프트에 넣는다
#     · system: "아래 문서 조각만 근거로 답해라. 조각에 답이 없으면 '문서에 없습니다'라고 답해라"
#     · user  : 문서 조각 + 질문
#   - ru.post_chat(messages)로 답변 받아 출력 (넣은 청크도 같이 출력해서 근거 확인)
#   - 질문은 두 개로 시작
#     · 답 있음 : "엔조의 이적료는 얼마야?"
#     · 답 없음 : "카마라의 주급은 얼마야?"
#
# 🔍 관찰
#   - 답 있는 질문: 답이 청크 내용과 일치하는가 (모델이 원래 알던 지식이 아니라 청크에서 왔는가)
#   - 답 없는 질문: "문서에 없다"고 하는가, 아니면 그럴듯한 숫자를 지어내는가
#   - (여유 있으면) system 프롬프트의 "없으면 모른다고 해라"를 빼면 결과가 달라지는가
#
# ✅ 결론 (openai/text-embedding-3-small, top_k=5, 청킹 3종으로 같은 질문 반복)
#   - 목적 두 개는 모두 확인됐다.
#     · 답 있음: "엔조의 맨시티 이적료는?" → 1억 2,500만 파운드. 모델 학습 이후 사건이라 청크에서 온 답
#     · 답 없음: "카마라의 주급은?" → 청킹 3종 모두 "문서에 없습니다"
#       "카마라"와 "주급"이 한 청크에 같이 있었는데도(주급은 발로건 얘기) 섞지 않았다
#       03에서 점수 0.40으로 통과시켰던 질문을 LLM은 걸러냈다
#     · 무관: "오늘 점심 뭐 먹을까?" → "문서에 없습니다"
#
#   - LLM은 받은 청크 안에서는 끝까지 정직했다. 실패는 전부 검색 쪽에서 났다.
#     · "엔조가 첼시로 올 때 이적료는?" — 실제 사건이라 모델이 원래 알 법한데도,
#       정답 청크가 안 들어온 overlap에서는 "문서에 없습니다"라고 했다 (지시를 지킴)
#     · 대신 fixed에서는 "1억 2,500만 - 약 1,800만 = 1억 700만"으로 청크끼리 엮어 계산해 맞혔다
#       → "조각만 근거로"라고 해도 조각 사이의 추론은 한다
#
#   - "문서에 없습니다"는 '문서에 없다'가 아니라 '받은 5개에 없다'는 뜻이다.
#     · "카마라 이적은 왜 무산됐어?"는 문서에 답이 있는데도 여러 번 "없다"고 했다
#     · 청킹 방식마다 놓친 이유가 달랐다
#         fixed 100자     : "상황에 / 서 협상을 중단시켰고" — 문장이 경계에서 잘림
#         overlap 100/20  : 거의 같은 청크가 쌍으로 top-5 자리를 차지 → 실제 정보는 3~4개 분량
#         separator(문단) : 정답 문단이 길고 주제가 많아(발로건·금액·메디컬·분노) 벡터가 흐려져 밀림
#     · 청크 크기는 "완결성 vs 선명함"의 트레이드오프. 공짜인 방식은 없었다
#     · separator에서 "엔조 첼시 이적료"는 원문 문단이 1위로 잡혀 직접 답했다 (fixed·overlap에선 놓침)
#
#   - 질문 표현도 검색을 흔든다.
#     · separator 기준 "카마라 이적이 빠다리난 이유는?" → 정답 문단 못 찾음 → "문서에 없습니다"
#     · 같은 내용을 "카마라 이적은 왜 무산되었지?"로 → 정답 문단 3위 → 과정까지 정확히 답함
#
#   - "문서 조각만 근거로, 없으면 없다고 해라"는 양날이다.
#     · 주급을 지어내지 않게 한 지시가, 점심 추천도 못 하게 막는다
#     · 지금 구조는 모든 질문을 무조건 검색 → 문서 기반 답변으로 보낸다. "검색할 질문인가"를 고르는 단계가 없다
#
#   - 정리: LLM은 판단·종합은 믿을 만하지만 받지 못한 정보는 만들지 못한다. 답의 상한은 검색이 정한다.
#
#   - 05로 가져갈 것
#     · 검색을 항상 켜는 파이프라인 대신 search_docs 툴로 만들어, 검색할지 말지를 LLM이 고르게 한다
#     · 검색이 아쉬우면: 질문 다시 쓰기(query rewrite) — 속어 실패를 고칠 수 있는지
# ============================================================
import os

import rag_utils as ru

if __name__ == "__main__":
    # 1. 캐시에서 chunks와 vectors 불러오기
    text = ru.load_text()
    
    chunks, vectors = ru.load_or_create_vector_store(text=text, method="separator")
    if chunks is None or vectors is None:
        print("벡터 스토어 생성에 실패했습니다.")
    else:
        print(f"Chunks: {chunks}")
        print(f"Vectors: {len(vectors)}개 (차원: {len(vectors[0])})")


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

        # 2. 모든 청크와 질문 벡터 간의 유사도 계산
        search_similarity = ru.search(question=question, chunks=chunks, vectors=vectors, top_k=5)

        # 3. 질문과 관련된 청크를 LLM에게 전달
        if not search_similarity:
            print("관련 문서 없음")

        else:
            message = []
            role_system = "system"
            role_user = "user"
            content = "\n".join([f"{i}. {chunk}" for i, (score, chunk) in enumerate(search_similarity, start=1)])

            prompt_messages = [
                {
                    "role": role_system, 
                    "content": "아래 문서 조각만 근거로 답해라. 없으면 '문서에 없습니다'라고 답해라"
                },
                {
                    "role": role_user,
                    "content": f"질문: {question}\n\n문서 조각 :\n{content}"
                }
            ]

            message.extend(prompt_messages)

            # 4. LLM에게 질문과 관련된 청크를 전달하고 답변 받기
            response = ru.post_chat(messages=message)
            answer = response["choices"][0]["message"]["content"]
            print(f"답변: {answer}")
            print(f"근거 문서 조각:\n{content}")
            print("=" * 50)