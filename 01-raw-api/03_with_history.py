# ============================================================
# 🧪 03. Multi-turn — 대화 히스토리 직접 관리하기
# ============================================================
# 🎯 목적
#   이전 대화를 messages에 실어 보내면 문맥이 이어진다.
#   02에서 못 알아듣던 질문이 통하는 것을 확인한다.
#
# 🧩 방법
#   messages 배열을 루프 밖에 두고 매 턴마다
#     1) 질문 append   { role: "user",      content: ... }
#     2) 요청 전송
#     3) 응답 append   { role: "assistant", content: ... }
#
# 🔍 확인할 것
#   - "그럼 거기 인구는?"  → 이번엔 알아들음
#   - prompt_tokens        → 턴이 쌓일수록 증가 (02는 제자리)
#   - 3) 을 주석 처리하면  → 02와 동일하게 동작
#
# 📮 POST {BASE_URL}/chat/completions
# ============================================================

import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_BASE_MODEL = os.getenv("OPENROUTER_BASE_MODEL")

if __name__ == "__main__":
    print("프로그램 실행 중... 종료하려면 'exit'를 누르세요.")
    
    # 대화 히스토리
    messages = []
    
    while True:
        # 질문
        question = input("질문을 입력하세요: ")
        
        if question.strip().lower() == "exit":
            print("프로그램을 종료합니다.")
            break
        
        # 1) 질문 append
        messages.append({
            "role": "user",
            "content": question
        })
        
        resp = httpx.post(
            url=f"{OPENROUTER_BASE_URL}/chat/completions",
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            data = json.dumps({
                "model": OPENROUTER_BASE_MODEL,
                "messages": messages
            })
        )
        
        print("json 요청 전문")
        print("--------------------------------------------")
        print(json.dumps({
            "model": OPENROUTER_BASE_MODEL,
            "messages": messages
        }, indent=4, ensure_ascii=False))
        
        if resp.status_code == 200:
            data = resp.json()
            answer = data['choices'][0]['message']['content']
            
            # 3) 응답 append
            # messages.append(data['choices'][0]['message'])
            
            usage_tokens_input = data['usage']['prompt_tokens']
            usage_tokens_output = data['usage']['completion_tokens']
            usage_costs = data['usage']['cost']
            
            print("응답:", answer)
            print(f"prompt token: {usage_tokens_input}, output token: {usage_tokens_output}, costs: {usage_costs}")
            print("--------------------------------------------")
        else:
            print("요청 실패:", resp.status_code, resp.text)