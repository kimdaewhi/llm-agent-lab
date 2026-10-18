# ============================================================
# 🦜 01_chat_model.py — Chat Model·Messages
# ============================================================
#
# LangChain에서 LLM을 호출하는 기본 단위
#
# 🎯 목적
#   - ChatOpenAI로 LLM 호출 방법 확인
#   - 반환 AIMessage 구조 확인
#
# 🔧 방법
#   - uv add langchain langchain-openai
#   - ChatOpenAI에 OpenRouter base_url 연결
#   - SystemMessage·HumanMessage 리스트로 invoke
#
# 🔍 관찰
#   - AIMessage의 content·response_metadata·usage_metadata
#
# ✅ 결론
#   - LangChain: LLM 호출·툴 정의·에이전트 루프·대화 기록 등 매번 반복하던 코드를 부품으로 제공하는 프레임워크
#   - 제공사(OpenAI·Anthropic·Google 등)가 달라도 invoke·AIMessage 같은 공통 인터페이스로 사용
# ============================================================
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_BASE_MODEL = os.getenv("OPENROUTER_BASE_MODEL")


if __name__ == "__main__":
    # 모델 객체 생성 — post_chat의 url·헤더·model 지정이 여기로 들어감
    model = ChatOpenAI(
        model=OPENROUTER_BASE_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
    )

    # 1. 문자열 하나로 호출 — 내부에서 HumanMessage 하나로 변환
    response = model.invoke("안녕? 한 문장으로 자기소개 해줘.")
    print("문자열 invoke 응답")
    print("--------------------------------------------")
    print(response.content)
    print()

    # 2. 메시지 리스트로 호출 — role dict 대신 메시지 클래스 사용
    messages = [
        SystemMessage(content="너는 주식 초보에게 설명하는 친절한 선생님이야. 두 문장 이내로 답해."),
        HumanMessage(content="PER이 뭐야?"),
    ]
    response = model.invoke(messages)

    # AIMessage 전체 구조
    print("AIMessage 전문")
    print("--------------------------------------------")
    print(repr(response))
    print()

    # 필드별 확인
    print("content           :", response.content)
    print("response_metadata :", response.response_metadata)
    print("usage_metadata    :", response.usage_metadata)