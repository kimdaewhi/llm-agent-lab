# ============================================================
# 🦜 04_memory.py — checkpointer
# ============================================================
#
# 01-raw-api에서 직접 하던 대화 기록 append를 LangChain에 위임
#
# 🎯 목적
#   - checkpointer·thread_id로 멀티턴 유지 여부 확인
#
# 🔧 방법
#   - create_agent에 checkpointer=InMemorySaver() 추가 (툴 없음)
#   - 같은 thread_id로 연속 질문
#     · "내 이름은 대휘야" → "내 이름 뭐라고?"
#   - 다른 thread_id로 "내 이름 뭐라고?" 질문
#
# 🔍 관찰
#   - 같은 thread_id에서 이름 기억 여부
#   - 턴마다 result["messages"] 길이 (이전 기록 누적 여부)
#   - thread_id가 다르면 기록이 끊기는지
# ============================================================
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_BASE_MODEL = os.getenv("OPENROUTER_BASE_MODEL")


def ask(agent, thread_id: str, question: str) -> None:
    """thread_id 대화방에 질문 하나를 보내고 답변·누적 메시지 수 출력"""
    config = {"configurable": {"thread_id": thread_id}}

    # 새 질문만 보냄 — 이전 기록은 checkpointer가 thread_id로 찾아서 앞에 붙임
    result = agent.invoke({"messages": [{"role": "user", "content": question}]}, config)
    messages = result["messages"]

    print(f"[{thread_id}] 질문: {question}")
    print(f"  답변: {messages[-1].content}")
    print(f"  누적 메시지 수: {len(messages)}")
    print()


if __name__ == "__main__":
    model = ChatOpenAI(
        model=OPENROUTER_BASE_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
    )

    agent = create_agent(
        model=model,
        tools=[],
        checkpointer=InMemorySaver(),
    )

    # 같은 thread_id — 앞 대화 이어짐
    ask(agent, "thread-A", "프랑스의 수도는?")
    ask(agent, "thread-A", "그럼 일본은?")

    # 다른 thread_id — 새 대화
    ask(agent, "thread-B", "그럼 독일은?")
