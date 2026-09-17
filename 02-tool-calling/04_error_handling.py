# ============================================================
# 🛡️ 04_error_handling.py — 도구 실행 실패 처리
# ============================================================
#
# 🎯 목적
#   - 도구가 예외를 던져도 프로세스가 죽지 않게 한다.
#   - 실패를 tool 결과로 되돌려 모델이 읽고 판단하게 한다.
#
# 🔧 방법
#   - 03 코드 그대로. tool_call 순회 안을 try/except로 감싼다.
#   - tool_call_id는 try 밖에서 꺼낸다. 실패해도 append해야 짝이 맞는다.
#   - 일부러 raise하는 도구로 실패를 만들고, 에러 문구를 바꿔가며 비교한다.
#
# 🔍 관찰
#   - try 범위 밖에서 예외가 날 때 동작
#   - 에러 문구에 따른 모델의 반응
#   - TOOL_MAPPING 등록 누락 시 동작
#   - max_steps 초과 후 다음 턴
#
# ✅ 결과
#   - try 범위: json.loads부터 실행까지. 밖에서 터지면 프로세스가 죽는다.
#   - 에러 메시지는 프롬프트다. 같은 실패라도 문구에 따라 결과가 갈림
#     내부 에러 → 인자 바꿔가며 헛발질 / 원인+대안 → 1바퀴에 정리
#   - 등록 누락은 예외가 아니라 else 경로. 조용히 실패해서 로그 없이는 못 찾는다.
#   - 모델은 에러 메시지도 검증 없이 믿는다. 틀린 안내를 주면 틀린 방향으로 움직임
#   - 루프가 어디서 끊기든 tool 메시지는 붙은 뒤라 히스토리는 유효했다.
#     단, 한도 초과 시 사용자에게 줄 답변은 따로 만들어야 한다.
# ============================================================

import os
import httpx
import json
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")



def print_messages(title: str, messages: list) -> None:
    print(f"[{title}] messages: {len(messages)}")
    print("-------------------------------------------------------------------")
    for i, m in enumerate(messages):
        role = m['role']
        
        if role == "tool":
            body = f"{m['tool_call_id'][:12]}... → {m['content']}"
        elif m.get('tool_calls'):
            calls = ", ".join(
                f"{c['function']['name']}{c['function']['arguments']}"
                for c in m['tool_calls']
            )
            body = f"tool_calls({len(m['tool_calls'])}): {calls}"
        else:
            body = m.get('content') or "(없음)"
        
        if len(body) > 120:
            body = body[:120] + "..."
        
        print(f"  {i} {role:<9} {body}")
    print("-------------------------------------------------------------------")


from datetime import datetime
from zoneinfo import ZoneInfo

def get_current_time(city: str = None) -> str:
    city_timezones = {
        "서울": "Asia/Seoul",
        "베이징": "Asia/Shanghai",
        "도쿄": "Asia/Tokyo",
        "뉴욕": "America/New_York",
        "런던": "Europe/London",
        "파리": "Europe/Paris",
        "베를린": "Europe/Berlin",
        "모스크바": "Europe/Moscow"
    }
    tz_name = city_timezones.get(city, "Asia/Seoul")
    
    current_time = datetime.now(ZoneInfo(tz_name)).strftime("%Y년 %m월 %d일 %H:%M:%S")
    return {
        "city": city,
        "current_time": current_time,
        "timezone": tz_name
    }


def get_weather(city: str = None) -> dict:    
    city_weather = {
        "서울":   {"condition": "맑음",       "temperature": 26.4, "humidity": 58},
        "베이징": {"condition": "구름 많음",   "temperature": 24.1, "humidity": 45},
        "도쿄":   {"condition": "흐림",       "temperature": 28.7, "humidity": 72},
        "뉴욕":   {"condition": "맑음",       "temperature": 23.2, "humidity": 51},
        "런던":   {"condition": "비",         "temperature": 16.8, "humidity": 84},
        "파리":   {"condition": "구름 조금",   "temperature": 19.5, "humidity": 63},
        "베를린": {"condition": "흐림",       "temperature": 17.3, "humidity": 70},
        "모스크바": {"condition": "맑음",      "temperature": 12.6, "humidity": 55},
    }
    
    if city not in city_weather:
        raise ValueError(f"'{city}'는 미지원. 조회 가능: 서울, 도쿄, 베이징, 뉴욕, 런던, 파리, 베를린, 모스크바")
    
    # if city not in city_weather:
    #     return {"error": f"'{city}'의 날씨 정보가 없습니다."}
    
    return {
        "city": city,
        **city_weather[city],
        "temperature_unit": "℃",
        "humidity_unit": "%",
    }


TOOL_MAPPING = {
    "get_current_time": get_current_time,
    "get_weather": get_weather,   # 등록 누락 실험: 이 줄을 주석 처리하면 else 경로로 빠진다
}



def post_request(messages, tools):
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
    
    if resp.status_code == 200:
        data = resp.json()
        return data 
    
    if resp.status_code != 200:
        print("요청 실패:", resp.status_code, resp.text)
        return None



if __name__ == "__main__":
    print("프로그램 실행 중... 종료하려면 'exit'를 입력하세요. 콘솔을 비우고 싶으면 'clear'를 입력하세요.")
    
    # 대화 히스토리
    messages = []
    
    while True:
        # 질문
        question = input("질문을 입력하세요: ")
        
        if question.strip().lower() == "exit":
            print("프로그램을 종료합니다.")
            break
        
        if question.strip().lower() == "clear":
            os.system('cls' if os.name == 'nt' else 'clear')
            print("콘솔을 비웠습니다. 계속 진행합니다.")
            continue
        
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
                        "properties": {
                            "city": {
                                "type": "string", 
                                "enum": ["서울", "베이징", "도쿄", "뉴욕", "런던", "파리", "베를린", "모스크바"],
                                "description": "도시명. 유저가 도시를 명시하지 않으면 알아서 추정해서 선택 가능"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "도시의 날씨 정보를 반환합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string", 
                                "enum": ["서울", "베이징", "도쿄", "뉴욕", "런던", "파리", "베를린", "모스크바"],
                                "description": "도시명. 유저가 도시를 명시하지 않으면 알아서 추정해서 선택 가능"
                            }
                        }
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
            print_messages("요청 전문", messages)
            data = post_request(messages, tools)
            
            if data is None:
                break
            
            print(f"finish_reason: {data['choices'][0]['finish_reason']}")
            messages.append(data['choices'][0]['message'])
            
            # 5) tool_calls 처리
            finish_reason = data['choices'][0]['finish_reason']
            
            if finish_reason == "tool_calls":
                tool_calls = data['choices'][0]['message']['tool_calls']
                
                # tool_calls 배열 전부 순회하여 모든 도구 호출 처리(다중 도구 호출(?))
                for tool_call in tool_calls:
                    tool_call_id = tool_call['id']
                    try:
                        tool_name = tool_call['function']['name']
                        tool_args = json.loads(tool_call['function']['arguments'])
                        
                        # 도구 실행
                        if tool_name in TOOL_MAPPING:
                            # 🏃🏻‍♂️ 실제 함수 실행
                            result = TOOL_MAPPING[tool_name](**tool_args)
                        else:
                            result = f"알 수 없는 도구: {tool_name}"
                    except Exception as e:
                        result = {"error": f"도구 실행 중 예외 발생: {str(e)}"}
                    
                    #결과를 role: "tool" 메시지로 append
                    messages.append({
                        "role": "tool",
                        "content": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False),
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