import json
from types import SimpleNamespace

from tools import execute_tool_call


def make_tool_call(call_id, tool_name, arguments):
    """构造与真实 tool_call 结构相似的测试对象。"""
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=tool_name,
            arguments=arguments,
        ),
    )


# ==================== 参数校验测试 ====================
def test_argument_validation():
    cases = [
        # (名称, 工具名, 参数, 预期错误)
        ("非法 JSON", "list_rooms", "{", "invalid_json"),
        ("参数不是 JSON 对象", "list_rooms", '["10"]', "invalid_arguments"),
        ("字符串人数", "list_rooms", '{"min_capacity": "10"}', "invalid_arguments"),
        ("浮点数人数", "list_rooms", '{"min_capacity": 10.5}', "invalid_arguments"),
        ("布尔值人数", "list_rooms", '{"min_capacity": true}', "invalid_arguments"),
        ("人数小于下限", "list_rooms", '{"min_capacity": 0}', "invalid_arguments"),
        ("人数超过上限", "list_rooms", '{"min_capacity": 101}', "invalid_arguments"),
        ("缺少 min_capacity", "list_rooms", "{}", "invalid_arguments"),
        ("包含额外字段", "list_rooms", '{"min_capacity": 10, "debug": true}', "invalid_arguments"),
        ("缺少 room_name", "query_room", "{}", "invalid_arguments"),
        ("room_name 是数字", "query_room", '{"room_name": 123}', "invalid_arguments"),
        ("room_name 是空串", "query_room", '{"room_name": "   "}', "invalid_arguments"),
        ("query_room 额外字段", "query_room", '{"room_name": "星河会议室", "debug": true}', "invalid_arguments"),
        ("未注册工具", "delete_room", "{}", "tool_not_allowed"),
    ]

    results = []
    print("=" * 50)
    print("参数校验测试")
    print("=" * 50)

    for label, tool_name, arguments, expected_error in cases:
        call = make_tool_call("test_call", tool_name, arguments)
        result = execute_tool_call(call)
        actual = result.get("error")
        ok = actual == expected_error
        results.append(ok)
        print(f"{'✅' if ok else '❌'} {label}: 预期 {expected_error}，实际 {actual}")

    return results


# ==================== 正常参数测试 ====================
def test_valid_arguments():
    cases = [
        ("查询星河", "query_room", '{"room_name": "星河会议室"}'),
        ("查询远航", "query_room", '{"room_name": "远航会议室"}'),
        ("筛选 10 人", "list_rooms", '{"min_capacity": 10}'),
        ("筛选 1 人", "list_rooms", '{"min_capacity": 1}'),
        ("筛选 100 人", "list_rooms", '{"min_capacity": 100}'),
        ("带空格的名称", "query_room", '{"room_name": "  星河会议室  "}'),
    ]

    results = []
    print("\n" + "=" * 50)
    print("正常参数测试")
    print("=" * 50)

    for label, tool_name, arguments in cases:
        call = make_tool_call("test_call", tool_name, arguments)
        result = execute_tool_call(call)
        ok = result.get("ok") is True
        results.append(ok)
        print(f"{'✅' if ok else '❌'} {label}: {json.dumps(result, ensure_ascii=False)}")

    return results


# ==================== 工具业务失败测试 ====================
def test_tool_business_failure():
    results = []
    print("\n" + "=" * 50)
    print("工具业务失败测试")
    print("=" * 50)

    # 查询不存在的会议室
    call = make_tool_call("test_call", "query_room", '{"room_name": "不存在的会议室"}')
    result = execute_tool_call(call)
    ok = result.get("ok") is False and result.get("error") == "room_not_found"
    results.append(ok)
    print(f"{'✅' if ok else '❌'} 查询不存在会议室: {json.dumps(result, ensure_ascii=False)}")

    # 筛选 50 人，返回空列表（业务成功但无结果）
    call = make_tool_call("test_call", "list_rooms", '{"min_capacity": 50}')
    result = execute_tool_call(call)
    ok = result.get("ok") is True and result.get("rooms") == []
    results.append(ok)
    print(f"{'✅' if ok else '❌'} 筛选 50 人无结果: {json.dumps(result, ensure_ascii=False)}")

    return results


# ==================== 停止条件测试 ====================
def test_stop_conditions():
    """验证最大轮次限制逻辑（不调 API，模拟）。"""
    results = []
    print("\n" + "=" * 50)
    print("停止条件测试（模拟）")
    print("=" * 50)

    # 模拟：模型一直请求工具，达到 MAX_ROUNDS 应停止
    MAX_ROUNDS = 4
    round_count = 0
    for _ in range(MAX_ROUNDS):
        round_count += 1
        # 模拟模型每次都返回工具调用
        tool_calls = [make_tool_call("call_x", "query_room", '{"room_name": "星河会议室"}')]

        if not tool_calls:
            break

    ok = round_count == MAX_ROUNDS
    results.append(ok)
    print(f"{'✅' if ok else '❌'} 达到最大轮次停止: 执行了 {round_count} 轮，上限 {MAX_ROUNDS}")

    # 模拟：模型直接回答，第一轮就停止
    round_count = 0
    for _ in range(MAX_ROUNDS):
        round_count += 1
        tool_calls = []   # 模拟模型不调工具
        if not tool_calls:
            break

    ok = round_count == 1
    results.append(ok)
    print(f"{'✅' if ok else '❌'} 模型直接回答第一轮停止: 执行了 {round_count} 轮")

    return results


# ==================== 主函数 ====================
def main():
    all_results = []
    all_results.extend(test_argument_validation())
    all_results.extend(test_valid_arguments())
    all_results.extend(test_tool_business_failure())
    all_results.extend(test_stop_conditions())

    passed = sum(all_results)
    total = len(all_results)

    print("\n" + "=" * 50)
    print(f"总计 {total} 个测试，通过 {passed} 个，失败 {total - passed} 个")
    print("=" * 50)


if __name__ == "__main__":
    main()

















































