import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, wait
from types import SimpleNamespace
from tools import LIST_ROOMS_TOOL, QUERY_ROOM_TOOL, execute_tool_call

# 本章提供给模型的工具：按名称查询 + 按容量筛选
TOOL_SCHEMAS = [QUERY_ROOM_TOOL, LIST_ROOMS_TOOL]

SYSTEM_PROMPT = "你是会议室助手。需要实时会议室数据时选择合适的工具。"

# 限制模型最多连续决策多少轮
MAX_ROUNDS = 4
# 限制单轮最多执行多少个工具
MAX_PARALLEL_CALLS = 4
# 整批任务的等待上限（秒），不是单个工具的内部超时
TOOL_BATCH_TIMEOUT = 5

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
model_name = os.getenv("OPENAI_MODEL")
base_url = os.getenv("BASE_URL")

if not api_key:
    raise ValueError("API key is required")
if not model_name:
    raise ValueError("Model name is required")
if not base_url:
    raise ValueError("Base url is required")

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=30.0,
    max_retries=2
)

user_text = input('你: ').strip()
if not user_text:
    raise ValueError("输入不能为空")

messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

# 最多执行 MAX_ROUNDS 轮，防止模型不断请求工具
for _ in range(MAX_ROUNDS):
    # 每一轮都把当前对话历史和全部工具说明交给模型
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        tools=TOOL_SCHEMAS,
        tool_choice="auto",
        parallel_tool_calls=False,
    )

    # 一条 assistant 消息包含本轮全部 tool_calls，因此只追加一次
    assistant_message = response.choices[0].message
    messages.append(assistant_message.model_dump(exclude_none=True))
    # 取出本轮全部工具调用，不能只读取 tool_calls[0]
    tool_calls = assistant_message.tool_calls or []
    if not tool_calls:
        print('直接回答:', assistant_message.content)
        break

    # 逐个校验并执行本轮的所有调用；此处仍是顺序执行
    for tool_call in tool_calls:
        result = execute_tool_call(tool_call)
        # assistant 只追加一次，但每个调用都要追加一条自己的 tool 结果
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
else:
    print("达到最大轮数，未得到最终回答")


def make_tool_call(call_id: str, tool_name: str, arguments_json: str):
    """构造与真实 tool_call 结构相似、但完全可控的测试对象。"""
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=tool_name, arguments=arguments_json),
    )



def execute_tool_calls_concurrently(tool_calls):
    # 调用数量超过上限时，整批拒绝执行
    if len(tool_calls) > MAX_PARALLEL_CALLS:
        return {
            call.id: {"ok": False, "error": "too_many_tool_calls"}
            for call in tool_calls
        }

    # 创建大小受控的线程池，并提交全部独立调用
    executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS)
    future_to_call = {
        executor.submit(execute_tool_call, call): call
        for call in tool_calls
    }

    # 在整批等待上限内，把任务分为已完成和未完成两组
    done, not_done = wait(
        future_to_call,
        timeout=TOOL_BATCH_TIMEOUT,
    )
    # 结果按 tool_call_id 保存，不能依赖线程完成顺序
    results_by_id = {}

    # 分别读取已经完成的调用结果
    for future in done:
        call = future_to_call[future]
        try:
            results_by_id[call.id] = future.result()
        except Exception:
            results_by_id[call.id] = {
                "ok": False,
                "error": "tool_failed",
            }

    # 超过整批等待上限的调用单独记录，不影响其他成功结果
    for future in not_done:
        call = future_to_call[future]
        future.cancel()
        results_by_id[call.id] = {
            "ok": False,
            "error": "batch_wait_timeout",
        }

    # 不继续等待未完成线程，并取消尚未开始的任务
    executor.shutdown(wait=False, cancel_futures=True)
    return results_by_id

# 并发函数返回“调用编号 → 结果”的映射
results_by_id = execute_tool_calls_concurrently(tool_calls)

# 按原始 tool_calls 顺序取回结果，并使用各自编号回传模型
for tool_call in tool_calls:
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(
                results_by_id[tool_call.id],
                ensure_ascii=False,
            ),
        }
    )










































