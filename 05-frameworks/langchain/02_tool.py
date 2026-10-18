# ============================================================
# 🦜 02_tool.py — @tool
# ============================================================
#
# 파이썬 함수를 LLM이 호출할 수 있는 툴로 변환
#
# 🎯 목적
#   - TOOL_DEFINITIONS 없이 @tool만으로 툴 동작 여부 확인
#   - bind_tools 후 LLM 응답 형태 확인
#
# 🔧 방법
#   - 03-agent-loop/01_agent_loop.py의 마인크래프트 툴 4종에 @tool 적용
#     · check_inventory / get_recipe / mine / craft
#   - 툴별 name·description·args 출력
#   - model.bind_tools(툴 4종)로 "다이아몬드 곡괭이 만들려면 뭐가 필요해?" invoke
#
# 🔍 관찰
#   - docstring·타입힌트가 스키마로 바뀐 결과
#     · 01_agent_loop.py의 TOOL_DEFINITIONS와 비교
#   - AIMessage.tool_calls 구조
#   - 툴 실제 실행 여부
#
# ✅ 결론
#   - @tool만으로 툴 동작 확인
#     · "다이아몬드 곡괭이 만들어줘" → check_inventory({}), get_recipe({'item': 'diamond_pickaxe'}) 호출 요청
#     · 함수명·docstring·타입힌트만으로 툴 선택·인자 생성
#   - 툴 호출 요청은 response.tool_calls에 파싱된 dict로 반환 (json.loads 불필요)
#     · 서로 의존 없는 툴 2개를 한 응답에 같이 요청 (병렬 툴 호출)
#   - 툴 실행은 여전히 내 코드 몫 → 실행·결과 전달이 없어 최종 답변(content) 없음
# ============================================================
import os

from dotenv import load_dotenv
from langchain.messages import HumanMessage, SystemMessage
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
# ⭐ LangChain을 쓰지 않았을 때는 TOOL_DEFINITION으로 일일히 도구를 정의해야 하지만
# LangChain의 @tool 데코레이터를 사용하면 함수 정의만으로 도구를 쉽게 등록할 수 있다.
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


# 시스템 프롬프트: 모델에게 역할과 행동 지침을 제공
SYSTEM_PROMPT = "너는 마인크래프트 크래프팅 도우미다. 레시피·인벤토리 확인, 채굴, 제작이 필요하면 제공된 도구를 사용한다."


if __name__ == "__main__":
    print("[LangChain Tools]")
    print("프로그램 실행 중... 종료하려면 'exit'를 입력하세요. 콘솔을 비우고 싶으면 'clear'를 입력하세요.")


    # 대화 히스토리
    messages = []
    model = ChatOpenAI(
        model=OPENROUTER_BASE_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
    )

    # 도구가 바인딩된 모델 생성
    model_with_tools = model.bind_tools([check_inventory, get_recipe, mine, craft])

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

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=question),
        ]
        response = model_with_tools.invoke(messages)

        # 도구 호출 요청 개수·내용
        print(f"도구 호출 요청: {len(response.tool_calls)}개")
        for tool_call in response.tool_calls:
            print(f"  - {tool_call['name']}({tool_call['args']})")

        # 최종 답변
        print("최종 답변:", response.content or "(없음)")
        print()