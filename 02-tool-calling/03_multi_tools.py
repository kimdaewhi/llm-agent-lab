# ============================================================
# 🔗 03_multi_tools.py — 다중 도구 호출 & 연쇄 호출
# ============================================================
#
# 🎯 목적
#   - 인자 있는 도구에서 arguments에 실제 값이 오는 걸 본다.
#   - 도구 여러 개 중 모델이 뭘 고르는지 본다.
#   - 앞 도구 결과가 뒤 호출에 반영되는 연쇄를 본다.
#
# 🔧 방법
#   - 02의 루프 그대로. 구조는 안 바뀐다.
#   - 도구 2개: get_current_time(city) / get_weather(city). 하드코딩 dict.
#   - parameters에 properties 채우고, 도시 목록은 enum으로 제한.
#   - tool_calls 배열 전부 순회. 호출 1개당 tool 메시지 1개.
#
# 🔍 관찰
#   - arguments에 담긴 값의 출처
#   - 한 응답에 오는 tool_calls 개수
#   - 루프가 도는 바퀴 수
#   - 없는 도시 조회 시 동작
#   - enum 적용 전후 차이
#
# ✅ 결과
#   - 인자 스키마: parameters.type은 항상 "object", 인자 타입은 properties 안쪽
#   - 인자 description: 문구에 따라 되묻기 / 추정 호출로 갈림
#   - enum: 고정 목록은 enum 필수. 없으면 12번 호출 중 3번만 유효
#   - 병렬 호출: tool_calls는 배열. 전부 순회, 짝 안 맞으면 400
#   - 연쇄 호출: 앞 바퀴 결과를 보고 다음 인자를 바꿔 재호출
#   - 결과 직렬화: dict 반환은 append 시점에 json.dumps
#   - 에러 처리: {"error": ...}도 정상 결과. 모델이 읽고 판단
# ============================================================

import os
import httpx
import json
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_BASE_MODEL = os.getenv("OPENROUTER_BASE_MODEL")



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
        return {"error": f"'{city}'의 날씨 정보가 없습니다."}
    
    return {
        "city": city,
        **city_weather[city],
        "temperature_unit": "℃",
        "humidity_unit": "%",
    }


TOOL_MAPPING = {
    "get_current_time": get_current_time,
    "get_weather": get_weather,
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
                    tool_name = tool_call['function']['name']
                    tool_args = json.loads(tool_call['function']['arguments'])
                    tool_call_id = tool_call['id']
                    
                    # 도구 실행
                    if tool_name in TOOL_MAPPING:
                        # 🏃🏻‍♂️ 실제 함수 실행
                        result = TOOL_MAPPING[tool_name](**tool_args)
                    else:
                        result = f"알 수 없는 도구: {tool_name}"
                    
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