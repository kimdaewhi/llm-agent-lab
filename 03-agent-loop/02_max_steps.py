# ============================================================
# 🔗 02_max_steps.py — 스텝 상한 & 미완료 처리
# ============================================================
#
# 01에서 max_steps를 넣었지만 실제로 걸려본 적은 없다.
# 그런데 상한에 걸리면 모델은 아직 도구를 부르는 중이고 최종 답변이 없다.
# 즉 "정상 종료"와 "중간에 끊김"은 전혀 다른 결과이고, 코드가 이를 구분해야 한다.
#
# 🎯 목적
#   - 상한 초과를 의도적으로 발생시켜 탈출 경로 확인
#   - 미완료 상태의 반환값 설계 (최종 답변 없음을 호출부에 알리기)
#   - 상한 값과 작업 난이도의 관계 파악
#
# 🔧 방법
#   - run_agent(user_input, max_steps=N)으로 상한을 인자화
#   - 반환값을 dict로: {"status": "done" | "max_steps", "content": ..., "steps": N}
#   - 같은 질문을 max_steps만 바꿔 반복 실행 (3 / 10 / 30)
#   - 탈출 시점의 messages 마지막 요소와 인벤토리 상태 출력
#   - 입력: "diamond_pickaxe 만들어줘" (연쇄가 20스텝 이상)
#
# 🔍 관찰
#   - max_steps=3 탈출 시 마지막 messages의 role과 content
#   - 같은 질문의 실행별 스텝 수 편차
#   - 중단 시점까지 인벤토리에 남은 변경 (부분 진행 상태)
#   - 탈출 직후 재요청 시 이어서 진행되는지
#
# ✅ 결론
#   - 상한 초과는 실패가 아니라 일시정지. 진행분은 messages에 남아 있다.
#   - 그래서 run_agent를 그대로 다시 부르면 중단 지점부터 이어진다.
#   - 단, 상한 체크가 루프 맨 위에 있을 때만. 도구 실행 중간에 끊으면
#     tool_calls ↔ tool 짝이 깨져 다음 요청이 거부된다.
#   - 반환을 dict(status)로 바꿔야 호출부가 재개/포기를 정할 수 있다.
#     None 하나로는 미완료인지 에러인지 구분이 안 된다.
#   - 재개마다 steps가 1부터 다시 센다. 총합은 호출부에서 누적해야 한다.
#   - 구조는 2단 루프. 안쪽은 자동, 바깥쪽은 사람 승인.
#     실무에선 바깥쪽 기준이 스텝 수가 아니라 비용이나 도구 위험도다.
# ============================================================
import os
import httpx
import json
from dotenv import load_dotenv
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")



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
            "model": "~openai/gpt-sol-latest",
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
        
        # message, tool 정의를 실어서 API 요청
        prnt_req_msg("요청 전문", messages)
        data = post_request(messages, TOOL_DEFINITIONS)
        
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