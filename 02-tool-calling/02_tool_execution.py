# ============================================================
# ⚙️ 02_tool_execution.py — 요청받은 도구를 실제로 실행해서 되돌려주기
# ============================================================
#
# 🎯 목적
#   - 01에서 받은 tool_calls를 실제 파이썬 함수 호출로 연결한다.
#   - 실행 결과를 role: "tool" 메시지로 되돌려 400 에러를 해소한다.
#   - 한 턴 안에서 API를 두 번 부르게 되는 구조를 직접 만들어본다.
#
# 🔧 방법
#   - get_current_time() 을 평범한 파이썬 함수로 정의한다. (datetime 사용)
#   - 함수 이름 문자열 → 실제 함수 객체를 잇는 다리를 만든다.
#     모델이 주는 건 "get_current_time" 이라는 문자열일 뿐이다.
#   - finish_reason 을 보고 분기한다.
#       "tool_calls" → 실행하고 결과 append 후 재요청
#       "stop"       → 사용자에게 출력하고 입력으로 복귀
#   - tool 메시지는 tool_call_id 로 요청과 짝을 맞춘다.
#
# 🔍 확인할 것
#   - role: "tool" 메시지에 어떤 필드가 필요한가
#   - 2차 요청의 messages 배열이 몇 개짜리로 조립되는가
#   - 2차 응답의 finish_reason 과 content
#   - 최종 답변에 실제 실행 결과가 반영되는가 (시스템 시간과 대조)
#   - tool 메시지의 content 자료형
#
# ✅ 결론
#   - tool_calls → 실행 → role:"tool" 로 결과 반환 → 재요청. 이 한 바퀴가 전부다.
#     API 호출 2번의 역할이 다르다. 1차는 "뭘 할까"(판단), 2차는 "뭐라고 답할까"(서술).
#     실행은 그 사이의 순수 로컬 작업이고 모델은 관여하지 않는다.
#   - tool 메시지는 role / tool_call_id / content(문자열) 세 개.
#     tool_call_id 로 요청과 짝이 맞아야 400이 안 난다.
#   - 모델은 도구 결과를 검증하지 않는다.
#     1999년을 돌려주니 "현재 시간은 1999년"이라고 그대로 답했다.
#     → 값의 정확성도, 실행 여부도 전부 개발자 책임이다.
#   - 한 턴을 완성할 때까지 도는 안쪽 루프가 생겼다. 이게 에이전트 루프의 원형.
#
# ⚠️ 관찰 주의
#   - 날씨 질문은 tools 유무와 무관하게 "모른다"고 답했다.
#     모델이 tools를 보고 경계를 인식한 게 아니라, 원래 그렇게 학습된 주제였다.
#     대조군 없이 해석하지 말 것.
#
# 👉 다음: 03 — 인자 있는 도구, 도구 여러 개, 그리고 도구 간 연쇄 호출
# ============================================================


import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_BASE_MODEL = os.getenv("OPENROUTER_BASE_MODEL")



def print_json(title: str, messages: object = None, tools: object = None) -> None:
    print(f"[{title}]")
    print("-------------------------------------------------------------------")
    print(json.dumps({
        "model": OPENROUTER_BASE_MODEL,
        "messages": messages,
        "tools": tools
    }, indent=4, ensure_ascii=False))
    print("-------------------------------------------------------------------")


def get_current_time() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y년 %m월 %d일 %H:%M:%S")
    # dt = datetime(1999, 1, 1, 0, 0, 0)
    # return dt.strftime("%Y년 %m월 %d일 %H:%M:%S")


TOOL_MAPPING = {
    "get_current_time": get_current_time,
}



def post_request(messages, tools):
    resp = httpx.post(
            url=f"{OPENROUTER_BASE_URL}/chat/completions",
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            data = json.dumps({
                "model": OPENROUTER_BASE_MODEL,
                "messages": messages,
                "tools": tools
            })
        )
    
    if resp.status_code == 200:
        data = resp.json()
        return data 
    
    if resp.status_code != 200:
        print("요청 실패:", resp.status_code, resp.text)
        return None



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
        
        # 3) 요청 & 응답 처리(응답에 tool_calls가 있으면 도구 실행 후 재요청)
        steps = 0
        while(True):
            steps += 1
            if steps > 5:
                print("도구 호출 반복 횟수가 너무 많습니다. 종료합니다.")
                break
            
            # 4) 요청
            print_json("요청 전문", messages, tools)
            data = post_request(messages, tools)
            
            if data is None:
                break
            
            messages.append(data['choices'][0]['message'])
            
            # 5) tool_calls 처리
            finish_reason = data['choices'][0]['finish_reason']
            if finish_reason == "tool_calls":
                tool_calls = data['choices'][0]['message']['tool_calls']
                tool_name = tool_calls[0]['function']['name']
                tool_args = json.loads(tool_calls[0]['function']['arguments'])
                tool_call_id = tool_calls[0]['id']
                
                # 도구 실행
                if tool_name in TOOL_MAPPING:
                    # 🏃🏻‍♂️ 실제 함수 실행
                    result = TOOL_MAPPING[tool_name](**tool_args)
                else:
                    result = f"알 수 없는 도구: {tool_name}"
                
                # 결과를 role: "tool" 메시지로 append
                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call_id
                })
                continue  # 재요청
            
            # 6) 응답 처리 
            else:
                answer = data['choices'][0]['message']['content']
                usage_tokens_input = data['usage']['prompt_tokens']
                usage_tokens_output = data['usage']['completion_tokens']
                usage_costs = data['usage']['cost']
                
                print("응답:", answer)
                print(f"prompt token: {usage_tokens_input}, output token: {usage_tokens_output}, costs: {usage_costs}")
                print("-------------------------------------------------------------------")
                break