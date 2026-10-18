# ============================================================
# 🦜 05_stock_agent.py — 주식 시세 에이전트
# ============================================================
#
# 01~04 개념 종합, 실제 데이터 기반의 작은 주식 시세 에이전트 구성
#
# 🎯 목적
#   - @tool·create_agent·checkpointer 조합으로 에이전트 구성
#
# 🔧 방법
#   - uv add yfinance
#   - 툴: get_price(ticker), get_financials(ticker) (yfinance)
#     · 한국 종목은 005930.KS 형식
#   - create_agent + checkpointer=InMemorySaver()
#   - 같은 thread_id로 연속 질문
#     · "엔비디아 PER 얼마야?" → "그럼 AMD는?"
#
# 🔍 관찰
#   - 질문별 툴 호출·ticker 인자
#   - "그럼 AMD는?"에서 앞 질문의 PER 맥락 유지 여부
# ============================================================
