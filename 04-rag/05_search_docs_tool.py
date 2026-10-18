# ============================================================
# 🧰 05_search_docs_tool.py — 검색을 툴로 바꿔 LLM이 쓸지 말지 고르게 하기
# ============================================================
#
# 04는 모든 질문을 무조건 검색 → "문서 조각만 근거로 답해라"로 보냈다.
# 그래서 주급은 안 지어냈지만, "오늘 점심 뭐 먹지?"에도 "문서에 없습니다"라고 했다.
# 검색을 항상 켜두는 대신 search_docs 툴로 만들어, 검색할 질문인지는 LLM이 판단하게 한다.
# 03-agent-loop의 루프 + 04의 search를 합치는 단계.
#
# 🎯 목적
#   - 검색할지 말지를 LLM이 스스로 고르는가
#     · 이적 사가 질문 → search_docs를 부르고 청크 근거로 답하는가
#     · 무관한 질문 → 툴 없이 그냥 답하는가
#
# 🔧 방법
#   - search_docs(query) 툴 하나
#     · 내부에서 ru.search(query, chunks, vectors, top_k=5) → 청크 텍스트만 번호 붙여 문자열로 반환
#     · chunks, vectors는 시작할 때 ru.load_or_create_vector_store(text, method="separator")로 한 번만 로드
#   - 툴 스키마의 description에 "무엇을 검색하는 툴인지"를 적는다
#     · 예: "2026 여름 엔조·카마라·발로건·리라 이적 사가 문서에서 관련 내용을 검색한다"
#   - system 프롬프트: "문서 관련 질문은 search_docs 결과만 근거로 답하고, 결과에 없으면 없다고 해라"
#     · 04처럼 "무조건 문서로만 답해라"가 아니라, 문서 질문일 때만 그렇게 하라는 것
#   - 03-agent-loop의 run_agent 루프 재사용 (finish_reason == "tool_calls"면 실행 후 다음 스텝)
#     · 스텝마다 툴 호출 여부와 LLM이 만든 query 인자를 출력
#   - 질문 3종
#     · 문서 질문 : "카마라 이적은 왜 무산됐어?"
#     · 답 없음   : "카마라의 주급은 얼마야?"
#     · 무관      : "오늘 점심 뭐 먹을까?"
#
# 🔍 관찰
#   - 질문별로 search_docs를 불렀는가 / 안 불렀는가
#   - LLM이 넘긴 query 인자가 사용자 질문 그대로인가, 다듬어졌는가
#     · 04에서 실패한 "카마라 이적이 빠다리난 이유는?"을 넣으면 query가 표준어로 바뀌어 검색이 살아나는가
#   - 무관한 질문에서 툴 없이 답했을 때, 04의 "문서에 없습니다"가 사라지는가
#
# ✅ 결론 (separator 청킹, top_k=5, OPENROUTER_MODEL 기준)
#   - 목적은 확인됐다. LLM이 검색할지 말지를 스스로 골랐다.
#     · 무관 : "오늘 점심 뭐 먹을까?", "비 오는데 집에서 뭐 하지?" → 툴 없이 바로 답함
#       04의 "문서에 없습니다"가 사라졌다
#     · 문서 : "카마라 이적은 왜 무산됐어?" → search_docs 호출 → 과정까지 정확히 답함
#     · 답 없음 : "카마라의 주급은?" → 검색 후 "문서에 없습니다" (04처럼 지어내지 않음)
#
#   - LLM이 query를 직접 만들면서 04의 검색 실패 일부가 풀렸다.
#     · "카마라 이적이 빠다리난 이유는?" → query "카마라 이적 무산 결렬 이유" → 정답
#       04에서는 질문 문장이 그대로 임베딩돼 실패했던 질문
#     · "엔조 사가의 재밌는 점은?" → query에 카마라·발로건·리라를 넣어 사가 전체로 넓혀 검색
#       → 연결된 문단을 엮어 의견까지 냄. "결과만 근거로"가 해석까지 막지는 않았다
#     · 다만 일정하지 않다. "발로건은 왜 삔또가 상했을까?"에서는 1차 query에 "삔또"가 그대로 남았다
#
#   - 결과가 모자라면 스스로 다시 검색했다. 04의 한 번 검색 구조에는 없던 동작
#     · 발로건 질문: 1차 결과가 카마라·엔조 위주 → 2차 query에 1차 결과의 단어(에버턴·스쿠루)를 가져와 재검색
#       → "에버턴 훈련장에서 이적 거부" 문단을 찾아 답함
#     · 그래도 정답에 가장 가까운 "발로건 거부 이유 추측" 문단은 두 번 다 못 가져왔다
#       → "기분이 상했다는 인과관계는 문서에서 확인되지 않는다"고 답함. 문서에는 있는데도
#     · 재검색은 검색 실패를 메워주지만 없애지는 못한다. 답의 상한은 여전히 검색이 정한다 (04 결론 그대로)
#
#   - 경계 질문에서는 "문서 질문인가"의 선이 단어에 끌려갔다.
#     · "첼시 26-27시즌 감독은 누구야?" → 사가 내용은 아닌데 search_docs 호출 → "문서에 없습니다"
#       description의 "이적 사가"보다 문서에 자주 나오는 "첼시"에 반응한 것으로 보인다
#     · 검색했는데 없으면 원래 알던 지식으로 넘어가지 않고 멈춘다
#       → 04의 "없으면 없다고 해라"의 양날이 사라진 게 아니라, 무관/관련의 경계로 자리만 옮겼다
#
#   - 멀티턴이 안 된다. 질문마다 messages를 새로 만들기 때문
#     · "이번 시즌 감독은?" → LLM이 "몇 시즌?"이라고 되물음 → "26-27시즌"이라고 답하자 "어느 팀?"이라고 다시 물음
#     · 앞 질문을 기억하지 못한다. 01-raw-api의 "LLM은 상태가 없다"를 다시 확인한 셈
#     · 이번에는 검색 결과가 섞이지 않게 일부러 끊었다. 이어 붙이면 이전 검색 결과까지 컨텍스트에 쌓인다
#
#   - 정리: 툴로 바꾸니까 "검색할지 말지"와 "무엇으로 검색할지"를 LLM이 맡게 됐다.
#     대신 그 판단은 description의 단어와 모델에 따라 흔들리고, 받지 못한 정보로는 여전히 답하지 못한다.
# ============================================================
import json
import os

import rag_utils as ru
import requests

# 시작할 때 한 번만 로드 — search_docs가 호출될 때마다 재사용
text = ru.load_text()
chunks, vectors = ru.load_or_create_vector_store(text=text, method="separator")


# ✨ search_docs 툴 — 검색 결과 청크를 번호 붙여 하나의 문자열로 반환
def search_docs(query: str) -> str:
    results = ru.search(question=query, chunks=chunks, vectors=vectors, top_k=5)
    if not results:
        return "검색 결과 없음"
    return "\n".join([f"{i}. {chunk}" for i, (score, chunk) in enumerate(results, start=1)])


TOOL_MAPPING = {
    "search_docs": search_docs,
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "2026 여름 엔조·카마라·발로건·리라 이적 사가 문서에서 관련 내용을 검색한다. "
                "이적료, 협상 과정, 이적 무산 이유 등 이 이적 사가에 대한 질문일 때 사용한다. "
                "관련 문서 조각 최대 5개를 번호 붙여 반환한다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "문서에서 찾을 내용. 검색이 잘 되도록 핵심 키워드 위주로 적는다.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "너는 사용자의 질문에 답하는 어시스턴트다. "
    "2026 여름 이적 사가(엔조·카마라·발로건·리라)에 관한 질문이면 search_docs로 검색하고, "
    "그 결과만 근거로 답해라. 결과에 답이 없으면 '문서에 없습니다'라고 답해라. "
    "이적 사가와 무관한 질문이면 툴 없이 평소처럼 답해라."
)


# ✨ 에이전트 루프 — 03-agent-loop의 run_agent에서 스텝별 툴 호출·query 출력만 남김
def run_agent(messages: list, max_steps: int = 5) -> str | None:
    for step in range(1, max_steps + 1):
        data = ru.post_chat(messages=messages, tools=TOOL_DEFINITIONS)
        if not data:
            print("API 요청 실패. 루프를 종료합니다.")
            return None

        finish_reason = data["choices"][0]["finish_reason"]
        message = data["choices"][0]["message"]
        messages.append(message)

        # tool_calls면 도구 실행 후 다음 스텝으로
        if finish_reason == "tool_calls":
            for call in message.get("tool_calls", []):
                tool_name = call["function"]["name"]
                try:
                    tool_args = json.loads(call["function"]["arguments"])
                    print(f"[step {step}] 툴 호출: {tool_name}({tool_args})")

                    if tool_name in TOOL_MAPPING:
                        tool_result = TOOL_MAPPING[tool_name](**tool_args)
                    else:
                        tool_result = f"알 수 없는 도구: {tool_name}"
                except (json.JSONDecodeError, TypeError, requests.RequestException) as e:
                    tool_result = f"도구 실행 중 예외 발생: {e}"

                print(f"[step {step}] 검색 결과:\n{tool_result}")
                messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": tool_result,
                    "tool_call_id": call.get("id"),
                })

        # 그 외 finish_reason이면 최종 답변 반환
        else:
            print(f"[step {step}] 툴 호출 없음 → 최종 답변")
            return message["content"]

    print(f"최대 스텝 수({max_steps})를 초과했습니다.")
    return None


if __name__ == "__main__":
    if chunks is None or vectors is None:
        print("벡터 스토어 생성에 실패했습니다.")
        raise SystemExit(1)

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

        # 질문마다 새 대화로 시작 — 이전 질문의 검색 결과가 섞이지 않게
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        answer = run_agent(messages)
        print(f"답변: {answer}")
        print("=" * 50)
