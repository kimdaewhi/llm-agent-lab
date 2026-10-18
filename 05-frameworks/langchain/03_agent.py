# ============================================================
# 🦜 03_agent.py — create_agent
# ============================================================
#
# 툴 호출 → 실행 → 결과 전달 루프를 LangChain에 위임
#
# 🎯 목적
#   - 02에서 멈춘 툴 호출 요청이 create_agent로 최종 답변까지 가는지 확인
#
# 🔧 방법
#   - 02_tool.py의 마인크래프트 툴 4종 그대로 사용
#   - create_agent(model, tools, system_prompt)로 에이전트 생성
#   - 툴 에러는 wrap_tool_call 미들웨어로 ToolMessage 변환
#   - "다이아몬드 곡괭이 만들어줘" invoke
#
# 🔍 관찰
#   - 반환 messages의 스텝별 툴 호출·결과
#   - 최종 답변·최종 인벤토리
#
# ✅ 결론
#   - create_agent = bind_tools된 모델 + 툴 실행기 + 루프
#     · invoke 한 번으로 "다이아몬드 곡괭이 만들어줘" → 제작 완료·최종 답변까지 진행
#     · system_prompt는 LLM 호출 때만 앞에 붙고 결과 messages에는 미포함
#   - result["messages"] 구조: human → (ai 툴 호출 요청 → tool 결과) 반복 → ai 최종 답변
#     · ai의 tool_calls[].id ↔ tool의 tool_call_id로 요청·결과 짝지음
#     · tool_calls가 빈 ai에서 루프 종료 → 최종 답변은 messages[-1].content
#   - 툴 예외는 기본값이면 그대로 던져져 에이전트 중단
#     · wrap_tool_call 미들웨어로 ToolMessage 변환 → LLM이 에러 메시지 보고 인자 수정 ("막대기" → "stick")
#   - 인자 값은 스키마에 유효 값이 없으면 질문 단어 그대로 사용
#     · docstring에 목록 기재 또는 Literal 타입힌트(enum)로 해결 가능
# ============================================================
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage
from langchain.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_BASE_MODEL = os.getenv("OPENROUTER_BASE_MODEL")


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
@tool
def check_inventory() -> dict:
    """현재 인벤토리 전체를 반환한다. 인자 없음."""
    return {
        "inventory": dict(INVENTORY),
        "total_item_types": len(INVENTORY),
    }


@tool
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


@tool
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


@tool
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


# 툴 에러 → ToolMessage 변환 (기본값은 예외를 그대로 던져 에이전트 중단)
# 에러 메시지를 LLM에게 돌려줘야 다음 행동(제작법 확인·재료 보충)을 고름
@wrap_tool_call
def handle_tool_errors(request, handler):
    try:
        return handler(request)
    except (ValueError, TypeError) as e:
        return ToolMessage(content=f"툴 에러: {e}", tool_call_id=request.tool_call["id"])


# 시스템 프롬프트: 모델에게 역할과 행동 지침을 제공
SYSTEM_PROMPT = "너는 마인크래프트 크래프팅 도우미다. 레시피·인벤토리 확인, 채굴, 제작이 필요하면 제공된 도구를 사용한다."


if __name__ == "__main__":
    model = ChatOpenAI(
        model=OPENROUTER_BASE_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
    )

    # 에이전트 생성 — 02의 bind_tools + 툴 실행 루프를 한 번에 대체
    agent = create_agent(
        model=model,
        tools=[check_inventory, get_recipe, mine, craft],
        system_prompt=SYSTEM_PROMPT,
        middleware=[handle_tool_errors],
    )

    question = input("질문을 입력하세요: ")

    # 루프 전체 실행 — 툴 호출이 없을 때까지 자동 반복
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})

    # 스텝별 툴 호출·결과
    for message in result["messages"]:
        if message.type == "ai" and message.tool_calls:
            for tool_call in message.tool_calls:
                print(f"[호출] {tool_call['name']}({tool_call['args']})")
        elif message.type == "tool":
            print(f"[결과] {message.content}")

    print()
    print("최종 답변:", result["messages"][-1].content)
    print("최종 인벤토리:", INVENTORY)
