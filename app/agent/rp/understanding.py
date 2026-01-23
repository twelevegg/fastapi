def update_understanding_level(state, agent_input):
    lvl = state["understanding_level"]

    if any(k in agent_input for k in ["데이터", "초과", "추가 요금", "추가요금"]):
        lvl = max(lvl, 1)

    if any(k in agent_input for k in ["GB", "기가", "기준", "까지", "한도"]):
        lvl = max(lvl, 2)

    if any(k in agent_input for k in ["사용하셨", "초과하셨", "사용량", "이용량", "10GB", "20GB", "5GB"]):
        lvl = max(lvl, 3)

    if any(k in agent_input for k in ["계산", "청구", "산정", "만원", "원", "요금이 붙"]):
        lvl = max(lvl, 4)

    state["understanding_level"] = lvl

def update_current_goal(state):
    lvl = state["understanding_level"]

    if lvl == 0:
        state["current_goal"] = "요금이 왜 이렇게 많이 나왔는지 이유를 알고 싶다"
    elif lvl == 1:
        state["current_goal"] = "데이터 초과가 무엇을 의미하는지 알고 싶다"
    elif lvl == 2:
        state["current_goal"] = "내 요금제의 기준 데이터량이 얼마인지 알고 싶다"
    elif lvl == 3:
        state["current_goal"] = "이번 달에 얼마나 초과 사용했는지 확인하고 싶다"
    else:
        state["current_goal"] = "이해했으니 통화를 마무리하고 싶다"

def update_ready_to_close(state):
    if state["understanding_level"] >= 4:
        state["ready_to_close"] = True
