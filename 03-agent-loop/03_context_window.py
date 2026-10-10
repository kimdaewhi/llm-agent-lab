# ============================================================
# 🔗 03_context_window.py — 히스토리 압축 & 짝 유지
# ============================================================
#
# 02에서 messages가 32개까지 늘고 prompt token이 2000을 넘었다.
# 서버는 기억이 없어 매 스텝 전체를 재전송하므로, 루프가 길수록 비용이 눈덩이가 된다.
# 그래서 보낼 때만 오래된 부분을 잘라낸다. 무엇을 버려도 되는지가 이 파일의 주제.
#
# 🎯 목적
#   - 스텝별 토큰 증가 추이 확인
#   - 코드 규칙으로 자르기 (모델에게 판단을 맡기지 않음)
#   - 잘라도 되는 것과 안 되는 것의 구분
#
# 🔧 방법
#   - compact(messages) 함수 추가 → post_request에 넘길 때만 적용
#     · 원본 messages는 그대로 유지 (자른 건 전송용 사본)
#   - 방식 1: 슬라이딩 윈도우 — 첫 user + 최근 N개만 남김
#   - 방식 2: 도구 결과 압축 — 오래된 tool의 content를 앞 100자로 자름
#   - assistant의 tool_calls와 짝인 tool 메시지는 항상 같이 처리
#   - 스텝마다 prompt_tokens 출력, 압축 전후 비교
#
# 🔍 관찰
#   - 압축 없음 / 방식 1 / 방식 2 의 총 토큰과 총 비용 차이
#   - 잘린 뒤 같은 도구를 다시 호출하는지 (스텝 수 증가)
#   - 짝이 깨졌을 때의 에러 응답
#   - 압축이 최종 결과물에 영향을 주는지
#
# ✅ 결론
#   - 두 가지 압축 방식
#     · 슬라이딩 윈도우 : 오래된 메시지를 버린다. 개수가 줄지만 짝이 깨질 수 있다.
#     · 도구 결과 축약   : tool의 content만 "(생략됨)"으로 바꾼다. 개수는 그대로라 안전하다.
#   - 원본 messages는 유지하고 전송용 사본만 압축한다. 잘라낸 건 되돌릴 수 없다.
#   - 짝이 깨지면 400. 자른 선두가 tool이나 tool_calls면 user까지 밀어야 한다.
#     단, 매 턴 도구 호출 패턴이 규칙적이면 경계가 잘 안 깨진다.
#   - 토큰은 도구 결과 축약이 확실히 줄었다. tool 본문이 히스토리 무게의 대부분.
#     슬라이딩 윈도우는 턴 수가 적으면 거의 효과가 없다.
#   - 단, 토큰 절감 ≠ 비용 절감. 압축이 prompt 앞부분을 매번 바꿔 캐시를 깬다.
#     토큰이 절반인데 비용이 더 나온 경우도 있었다.
#     → 경계를 매 스텝 옮기지 말고 임계치를 넘을 때만 크게 생략하는 편이 낫다.
#   - 도구 결과가 생략되면 모델은 조회를 다시 하거나, 자기 이전 답변 텍스트를 근거로 판단한다.
# ============================================================
import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")



def prnt_req_msg(title: str, messages: list) -> None:
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
        
        print(f"[{i:02d}] {role}: {body}")
    print("-------------------------------------------------------------------\n")



def prnt_resp_msg(message: dict) -> None:
    """assistant 메시지에서 암호화 블록·빈 필드를 제외하고 출력한다."""
    SKIP_KEYS = {"reasoning_details", "refusal"}
    
    if not isinstance(message, dict):
        print(f"메시지 : {message}")
        return
    
    cleaned = {
        k: v for k, v in message.items()
        if k not in SKIP_KEYS and v is not None
    }
    
    print(f"메시지 : {cleaned}")

# ============================================================
# 🧱 마인크래프트 크래프팅 데이터 (외부 의존 없이 전부 하드코딩)
# ============================================================

# 제작 가능한 아이템만 등록한다.
# 원목/돌/철광석/다이아몬드는 여기 없다 → 채굴(mine)로만 얻는다.
# 상위 곡괭이가 하위 곡괭이를 재료로 요구하지 않는다. 등급 제약은 MINEABLE에만 있다.
# 재료 설명 : 
#  - oak_planks : 나무판자
#  - stick : 막대기
#  - wooden_pickaxe : 나무 곡괭이
#  - stone_pickaxe : 돌 곡괭이
#  - iron_pickaxe : 철 곡괭이
#  - diamond_pickaxe : 다이아몬드 곡괭이
# ============================================================
#  - log : 원목
#  - stone : 돌
#  - iron_ore : 철광석
#  - diamond : 다이아몬드

RECIPES = {
    "oak_planks":       {"materials": {"log": 1},                       "result_count": 4},
    "stick":            {"materials": {"oak_planks": 2},                "result_count": 4},
    "wooden_pickaxe":   {"materials": {"oak_planks": 3, "stick": 2},    "result_count": 1},
    "stone_pickaxe":    {"materials": {"stone": 3, "stick": 2},         "result_count": 1},
    "iron_pickaxe":     {"materials": {"iron_ore": 3, "stick": 2},      "result_count": 1},
    "diamond_pickaxe":  {"materials": {"diamond": 3, "stick": 2},       "result_count": 1},
}

# 채굴 가능한 블록 → 필요한 곡괭이 (None이면 맨손 채굴)
MINEABLE = {
    "log": None,
    "stone": "wooden_pickaxe",
    "iron_ore": "stone_pickaxe",
    "diamond": "iron_pickaxe",
}

# 전역 상태. mine/craft가 이 dict를 직접 수정한다.
# oak_planks 2개 = diamond_pickaxe까지 딱 떨어지는 최소량 (헛 제작하면 oak_planks를 더 캐야 한다)
INVENTORY = {"log": 2}


def _unknown_item_error(item: str) -> ValueError:
    """레시피에 없는 아이템 → 채굴 재료인지 오타인지 구분해서 안내한다."""
    if item in MINEABLE:
        return ValueError(
            f"'{item}'은(는) 제작이 아니라 채굴로 얻는 재료입니다. "
            f"mine 도구를 사용하세요. 채굴 가능: {', '.join(MINEABLE)}"
        )
    return ValueError(
        f"'{item}' 레시피가 없습니다. "
        f"제작 가능: {', '.join(RECIPES)} / 채굴 가능: {', '.join(MINEABLE)}"
    )


# ============================================================
# 🛠️ 도구 4종
# ============================================================

def check_inventory() -> dict:
    """현재 인벤토리 전체를 반환한다. 인자 없음."""
    return {
        "inventory": dict(INVENTORY),
        "total_item_types": len(INVENTORY),
    }


def get_recipe(item: str) -> dict:
    """아이템 1배치 제작에 필요한 재료와 결과 개수를 반환한다."""
    if item not in RECIPES:
        raise _unknown_item_error(item)
    
    recipe = RECIPES[item]
    return {
        "item": item,
        "materials": dict(recipe["materials"]),
        "result_count": recipe["result_count"],
    }


def mine(block: str, count: int = 1) -> dict:
    """블록을 채굴해 인벤토리에 넣는다. 필요한 곡괭이가 없으면 실패한다."""
    if block not in MINEABLE:
        raise ValueError(
            f"'{block}'은(는) 채굴할 수 없습니다. 채굴 가능: {', '.join(MINEABLE)}"
        )
    
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError(f"count는 1 이상의 정수여야 합니다. 받은 값: {count!r}")
    
    # 에러 메시지는 프롬프트다. 원인(어떤 곡괭이)과 대안(다음에 할 일)을 같이 준다.
    required = MINEABLE[block]
    if required and INVENTORY.get(required, 0) < 1:
        raise ValueError(
            f"'{block}' 채굴에 필요한 '{required}'이(가) 인벤토리에 없습니다. "
            f"get_recipe('{required}')로 제작법을 확인한 뒤 craft하세요."
        )

    INVENTORY[block] = INVENTORY.get(block, 0) + count
    return {
        "mine": block,
        "count": count,
        "used_tool": required or "맨손",
        "inventory": dict(INVENTORY),
    }


def craft(item: str) -> dict:
    """레시피 1배치를 제작한다. 재료를 차감하고 결과물을 인벤토리에 넣는다."""
    if item not in RECIPES:
        raise _unknown_item_error(item)
    
    recipe = RECIPES[item]
    materials = recipe["materials"]
    
    # 부족한 재료는 한 번에 전부 알려준다. 하나씩 알려주면 모델이 한 재료씩 헛발질한다.
    missing = {
        name: need - INVENTORY.get(name, 0)
        for name, need in materials.items()
        if INVENTORY.get(name, 0) < need
    }
    if missing:
        need_text = ", ".join(f"{name} {n}개" for name, n in materials.items())
        missing_text = ", ".join(f"{name} {n}개" for name, n in missing.items())
        raise ValueError(
            f"'{item}' 제작 실패. 필요한 재료: {need_text}. "
            f"부족한 재료: {missing_text}. 현재 인벤토리: {INVENTORY}"
        )
    
    for name, need in materials.items():
        INVENTORY[name] -= need
        if INVENTORY[name] <= 0:
            del INVENTORY[name]
    
    INVENTORY[item] = INVENTORY.get(item, 0) + recipe["result_count"]
    return {
        "craft": item,
        "count": recipe["result_count"],
        "used_materials": dict(materials),
        "inventory": dict(INVENTORY),
    }



# ==================================== 도구 매핑 ==================================== #
TOOL_MAPPING = {
    "check_inventory": check_inventory,
    "get_recipe": get_recipe,
    "mine": mine,
    "craft": craft,
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": (
                "현재 인벤토리에 어떤 아이템이 몇 개 있는지 확인한다. "
                "제작이나 채굴을 시도하기 전에 재료 보유량을 먼저 파악할 때 사용한다. "
                "인벤토리를 변경하지 않는다."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recipe",
            "description": (
                "아이템 1배치 제작에 필요한 재료와 결과 개수를 조회한다. "
                "무엇이 필요한지 모르는 상태에서 craft를 시도하지 말고 이 도구로 먼저 확인한다. "
                "인벤토리를 변경하지 않는다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "enum": list(RECIPES),
                        "description": "제작법을 조회할 아이템 이름.",
                    },
                },
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mine",
            "description": (
                "블록을 채굴해 인벤토리에 넣는다. 제작으로 얻을 수 없는 원재료는 이 도구로만 얻는다. "
                "블록마다 요구하는 곡괭이 등급이 다르며, 해당 곡괭이가 인벤토리에 없으면 실패한다. "
                "곡괭이가 없다면 먼저 그 곡괭이를 제작해야 한다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "block": {
                        "type": "string",
                        "enum": list(MINEABLE),
                        "description": "채굴할 블록 이름.",
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "채굴할 개수. 생략하면 1개. "
                            "필요한 수량을 이미 알고 있다면 한 번에 지정하는 편이 호출 횟수를 줄인다."
                        ),
                    },
                },
                "required": ["block"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "craft",
            "description": (
                "레시피 1배치를 제작한다. 재료를 인벤토리에서 차감하고 결과물을 넣는다. "
                "재료가 하나라도 부족하면 실패하므로, 부족하다면 하위 아이템을 먼저 제작하거나 "
                "원재료를 채굴해 확보한 뒤 다시 시도한다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "enum": list(RECIPES),
                        "description": "제작할 아이템 이름.",
                    },
                },
                "required": ["item"],
            },
        },
    },
]




# OpenRouter API 요청 함수
def post_request(messages, tools):
    resp = httpx.post(
        url=f"{OPENROUTER_BASE_URL}/chat/completions",
        
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        
        data=json.dumps({
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "tools": tools
        })
    )
    
    if resp.status_code != 200:
        print("요청 실패:", resp.status_code, resp.text)
        return None
    
    if resp.status_code == 200:
        data = resp.json()
        return data


# Context Window 압축 함수
def compact(messages: list, max_user_messages=3) -> list:
    """messages를 압축하여 반환한다.
    
    - 최근 user 메시지 N개와 그 이후 메시지만 남긴다 (더 오래된 건 버림)
    - 경계가 항상 user 앞이라 assistant의 tool_calls ↔ tool 짝은 깨지지 않는다
    """
    compacted = []
    user_count = 0
    
    for msg in reversed(messages):
        if msg['role'] == 'user':
            if user_count == max_user_messages:
                break
            user_count += 1
        
        compacted.append(msg)
    
    # 역순으로 다시 정렬
    compacted.reverse()
    
    return compacted


# 오래된 tool 메시지의 content만 축약하는 함수
def compact_tools(messages: list, keep_recent=6) -> list:
    """오래된 tool 메시지의 content만 축약한다. 개수는 유지."""
    compacted = []
    total = len(messages)
    
    for i, msg in enumerate(messages):
        if msg['role'] == 'tool' and i < total - keep_recent:
            # 오래된 tool 메시지의 content를 통째로 (생략됨)으로 대체
            compacted.append({**msg, 'content': '(생략됨)'})
        else:
            compacted.append(msg)
            
    return compacted



def run_agent(messages: list, max_steps=10) -> dict:
    curr_step = 0
    
    result = None
    while True:
        curr_step += 1
        
        # 루프 탈출 조건: 최대 스텝 수 초과
        if curr_step > max_steps:
            print(f"최대 스텝 수({max_steps})를 초과했습니다. 루프를 종료합니다.")
            result = { "status": "max_steps", "content": None, "steps": curr_step - 1 }
            return result
        
        
        # ⭐ 방식 1 : sliding window 방식 : 최근 user 메시지 N개와 그 이후만 남김
        # compact_message = compact(messages, max_user_messages=5)
        
        # ⭐ 방식 2 : 오래된 tool 메시지의 content만 축약
        # compact_message = compact_tools(messages, keep_recent=6)
        
        ## ⭐ 방식 3 : 두 가지 방식 결합
        compact_message = compact_tools(compact(messages, max_user_messages=5), keep_recent=6)
        
        # message, tool 정의를 실어서 API 요청
        prnt_req_msg("요청 전문", compact_message)
        data = post_request(compact_message, TOOL_DEFINITIONS)
        
        if data is None:
            print("API 요청 실패. 루프를 종료합니다.")
            result = { "status": "api_error", "content": None, "steps": curr_step - 1 }
            return result
        
        finish_reason = data["choices"][0]["finish_reason"]
        message = data["choices"][0]["message"]
        prnt_resp_msg(message)
        
        messages.append(message)
        
        # tool_calls면 도구 실행 후 다음 스텝으로
        if finish_reason == "tool_calls":
            tool_calls = message.get("tool_calls", [])
            for call in tool_calls:
                tool_name = call["function"]["name"]
                tool_call_id = call.get("id")
                try:
                    tool_args = json.loads(call["function"]["arguments"])
                    
                    if tool_name in TOOL_MAPPING:
                        tool_result = TOOL_MAPPING[tool_name](**tool_args)
                    else:
                        tool_result = f"알 수 없는 도구: {tool_name}"
                except Exception as e:
                    tool_result = {"error": f"도구 실행 중 예외 발생: {str(e)}"}
                
                messages.append({
                    "role": "tool", 
                    "name": tool_name, 
                    "content": json.dumps(tool_result, ensure_ascii=False), 
                    "tool_call_id": tool_call_id
                })
                
        # 그 외 finish_reason이면 최종 답변 반환 후 루프 종료
        else:
            answer = message['content']
            usage_tokens_input = data['usage']['prompt_tokens']
            usage_tokens_output = data['usage']['completion_tokens']
            usage_costs = data['usage']['cost']
            
            print("응답:", answer)
            print(f"prompt token: {usage_tokens_input}, output token: {usage_tokens_output}, costs: {usage_costs}")
            print("-------------------------------------------------------------------")
            
            result = { "status": "done", "content": answer, "steps": curr_step }
            return result


if __name__ == "__main__":
    print("프로그램 실행 중... 종료하려면 'exit'를 입력하세요. 콘솔을 비우고 싶으면 'clear'를 입력하세요.")
    
    # 대화 히스토리
    messages = []
    
    max_steps = 5
    
    while True:
        # 질문
        question = input("질문을 입력하세요: ")
        
        # 종료
        if question.strip().lower() == "exit":
            print("프로그램을 종료합니다.")
            break
        
        # 콘솔 클리어
        if question.strip().lower() == "clear":
            os.system('cls' if os.name == 'nt' else 'clear')
            print("콘솔을 비웠습니다. 계속 진행합니다.")
            continue
        
        # 대화 히스토리 및 인벤토리 초기화
        if question.strip().lower() == "reset":
            messages = []
            INVENTORY.clear()
            INVENTORY.update({"log": 2})
            print("대화 히스토리와 인벤토리를 초기화했습니다.")
            continue
        
        # 1) 질문 append
        messages.append({"role": "user", "content": question})
        
        
        # 2) Agent Loop
        answer = run_agent(messages, max_steps)
        
        # 3) 결과 처리
        while answer["status"] == "max_steps":
            print(f"미완료 — {answer['steps']}스텝까지 진행")
            if input("이어서 진행할까요? (y/n): ").strip().lower() != "y":
                break
            answer = run_agent(messages, max_steps)
            
        if answer["status"] == "done":
            print(f"최종 답변: {answer['content']}")
            print(f"총 스텝 수: {answer['steps']}")
            
        elif answer["status"] == "api_error":
            print("API 요청 중 오류가 발생하여 루프가 종료되었습니다.")