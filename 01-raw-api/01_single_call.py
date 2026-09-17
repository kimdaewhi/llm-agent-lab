# ============================================================
# 🧪 01. 단일 호출 — 질문 한 번 던지고 응답 받기 (httpx)
# ============================================================
# 🎯 목적
#   LLM API가 특별한 무엇이 아니라, 인증 헤더 붙은 평범한
#   JSON POST 하나라는 것을 직접 확인한다.
#
# 🔍 확인할 것
#   - choices      : 항상 배열 (n 파라미터로 후보 여러 개를 받을 수 있어서)
#   - finish_reason: 응답이 왜 끝났는지 (stop / length / tool_calls ...)
#   - usage        : 이번 요청에 쓴 토큰 수 = 비용의 근거
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


if __name__ == "__main__":
    # 질문
    question = input("질문을 입력하세요: ")
    
    response = httpx.post(
        # 요청 url
        url=f"{OPENROUTER_BASE_URL}/chat/completions",
        
        # 요청 헤더
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        
        data = json.dumps({
            "model": "~openai/gpt-sol-latest",
            "messages": [
                {
                    "role": "user", 
                    "content": question
                }
            ]
        })
    )
    
    data = response.json()
    
    print("json 응답 전문")
    print("--------------------------------------------")
    print(json.dumps(data, indent=4, ensure_ascii=False))
    
    # 응답 확인
    if response.status_code == 200:
        data = response.json()
        answer = data['choices'][0]['message']['content']
        print("응답:", answer)
    else:
        print("요청 실패:", response.status_code, response.text)