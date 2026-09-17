# ============================================================
# 🧰 01_tool_schema.py — 도구를 "쥐여주기만" 해보기
# ============================================================
#
# 🎯 목적
#   - 01-raw-api에서 확인한 "모르는 건 지어낸다"를 도구로 넘길 수 있는지 본다.
#   - tools 스펙을 request body에 추가했을 때 응답 JSON이 어떻게 달라지는지 확인한다.
#   - 도구 호출은 모델이 "실행"하는 게 아니라 "실행해달라고 요청"하는 것임을 눈으로 본다.
#
# 🔧 방법
#   - 01-raw-api의 최소 httpx POST 코드를 그대로 가져온다.
#   - body에 tools 배열을 추가한다. 도구는 1개, get_current_time 정도로 단순하게.
#     (모델이 절대 알 수 없는 값 → 도구를 쓸 수밖에 없는 상황을 만든다)
#   - 함수 본체는 아직 만들지 않는다. JSON 스펙만 선언한다.
#   - 응답을 content만 뽑지 말고 message 객체 전체를 그대로 출력한다.
#
# 🔍 확인할 것
#   - finish_reason 값이 뭐로 오는가
#   - message.content 에는 뭐가 들어있는가
#   - tool_calls 의 구조 (id / type / function.name / function.arguments)
#   - arguments 의 자료형
#   - tools 를 빼고 같은 질문을 던지면 어떻게 되는가 (대조군)
#   - 도구가 필요 없는 질문에는 어떻게 반응하는가
#
# ✅ 결론
#   - 모델은 도구를 실행하지 않는다. tool_calls(이름 + arguments)로 "실행해달라"고 요청만 한다.
#     finish_reason: "tool_calls", content: null, arguments는 dict가 아니라 JSON 문자열.
#   - tool_calls 뒤에 그 결과(role: "tool")가 없는 채로 다음 요청을 보내면 400.
#     → "No tool output found for function call {id}"
#     messages 배열을 유효한 상태로 유지하는 건 전적으로 내 책임이다.
#   - 어떤 도구를 쓸지는 모델이 질문과 description을 보고 판단한다.
#     무관한 질문에 tools가 붙어 있어도 그냥 무시하고 평범하게 답한다.
#     → 매 요청에 tools를 넣고 판단은 모델에게 맡기면 된다.
#
# 👉 다음: 02 — tool_calls를 실제 함수 실행으로 연결하고, 결과를 되돌려 최종 답변까지 받기
# ============================================================
import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")

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
            "content": question,
        })
        
        # 2) tool calling 추가
        tools = [{
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "현재 시간을 반환합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]
        
        resp = httpx.post(
            url=f"{OPENROUTER_BASE_URL}/chat/completions",
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            data = json.dumps({
                "model": "~openai/gpt-sol-latest",
                "messages": messages,
                "tools": tools
            })
        )
        
        print("json 요청 전문")
        print("-------------------------------------------------------------------")
        print(json.dumps({
            "model": "~openai/gpt-sol-latest",
            "messages": messages,
            "tools": tools
        }, indent=4, ensure_ascii=False))
        print("-------------------------------------------------------------------")
        
        
        if resp.status_code == 200:
            data = resp.json()
            answer = data['choices'][0]['message']['content']
            
            # 3) 응답 append
            messages.append(data['choices'][0]['message'])
            
            usage_tokens_input = data['usage']['prompt_tokens']
            usage_tokens_output = data['usage']['completion_tokens']
            usage_costs = data['usage']['cost']
            
            print("응답 전문")
            print(json.dumps(data, indent=4, ensure_ascii=False))
            print("-------------------------------------------------------------------")
            print("응답:", answer)
            print(f"prompt token: {usage_tokens_input}, output token: {usage_tokens_output}, costs: {usage_costs}")
            print("-------------------------------------------------------------------")
        else:
            print("요청 실패:", resp.status_code, resp.text)