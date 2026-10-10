# ============================================================
# 🧪 02. Stateless — 서버는 이전 대화를 기억하지 않는다
# ============================================================
# 🎯 목적
#   같은 세션처럼 보이게 질문을 이어서 던져보고,
#   모델이 앞의 대화를 전혀 모른다는 것을 직접 확인한다.
#
# 🧩 방법
#   1차) messages = [ {user: "일본의 수도는?"} ]        → "도쿄입니다"
#   2차) messages = [ {user: "거기 인구는 몇 명이야?"} ] → ???
#   ※ 2차 요청에 1차 내용을 일부러 넣지 않는다
#
# 🔍 확인할 것
#   - 응답 내용     : "거기가 어디를 말하는 건가요?" 류로 되물어옴
#   - prompt_tokens : 2차도 1차와 비슷한 수준 → 서버에 쌓인 게 없다는 증거
#   - id            : 매번 다름 → 두 요청은 서로 남남
#
# 💡 결론
#   세션도 대화 ID도 없다. 대화가 이어지는 건 클라이언트가
#   매번 전부 다시 보내주기 때문 → 03에서 확인
# ============================================================

import msvcrt
import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")


if __name__ == "__main__":
    print("프로그램 실행 중... 종료하려면 'exit'를 누르세요.")
    
    while True:
        # 질문
        question = input("질문을 입력하세요: ")
        
        if question.strip().lower() == "exit":
            print("프로그램을 종료합니다.")
            break
        
        resp = httpx.post(
            url=f"{OPENROUTER_BASE_URL}/chat/completions",
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            data = json.dumps({
                "model": OPENROUTER_MODEL,
                "messages": [
                    {
                        "role": "user", 
                        "content": question
                    }
                ]
            })
        )
        
        # 응답 확인
        if resp.status_code == 200:
            data = resp.json()
            answer = data['choices'][0]['message']['content']
            usage_tokens_input = data['usage']['prompt_tokens']
            usage_tokens_output = data['usage']['completion_tokens']
            usage_costs = data['usage']['cost']
            
            print("응답:", answer)
            print(f"prompt token: {usage_tokens_input}, output token: {usage_tokens_output}, costs: {usage_costs}")
            print("--------------------------------------------")
        else:
            print("요청 실패:", resp.status_code, resp.text)
            break