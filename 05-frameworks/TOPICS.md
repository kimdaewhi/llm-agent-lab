# 05-frameworks 실습 주제

LangChain 개념 하나씩 실습 후, 마지막에 작은 주식 시세 에이전트로 종합.
1~5는 더미 툴(고정 값 반환), 6에서만 yfinance 사용.

| 순서 | 파일 | 개념 | 확인할 것 |
|---|---|---|---|
| 1 | `langchain/01_chat_model.py` | Chat Model·Messages | `invoke` 호출, `AIMessage` 구조 |
| 2 | `langchain/02_tool.py` | `@tool` | 툴 스키마, `bind_tools` 툴 호출 응답 |
| 3 | `langchain/03_agent.py` | `create_agent` | 툴 호출부터 최종 답까지 자동 루프 |
| 4 | `langchain/04_structured_output.py` | `response_format` | 최종 답의 Pydantic 객체 반환 |
| 5 | `langchain/05_memory.py` | checkpointer | `thread_id`로 대화 유지 |
| 6 | `langchain/06_stock_agent.py` | 종합 | yfinance 툴 + 1~5 개념 |
