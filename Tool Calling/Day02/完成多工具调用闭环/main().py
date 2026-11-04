import json
import os
from dotenv import load_dotenv
from openai import OpenAI

from tools import TOOL_SCHEMAS, execute_tool_call
from concurrent.futures import ThreadPoolExecutor, wait


SYSTEM_PROMPT = "你是会议室助手。需要实时会议室数据时选择合适的工具，语句简单易懂。"

MAX_ROUNDS = 4
MAX_PARALLEL_CALLS = 4
TOOL_BATCH_TIMEOUT = 5

load_dotenv()
api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
model_name = (os.getenv("OPENAI_MODEL") or "").strip()
base_url = (os.getenv("BASE_URL") or "").strip()

if not api_key:
    raise RuntimeError("请先设置 OPENAI_API_KEY")
if not model_name:
    raise RuntimeError("请先设置 OPENAI_MODEL")
if not base_url:
    raise RuntimeError("请先设置 BASE_URL")

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=30.0,
    max_retries=2
)

# ==================== 受控并发执行 ====================
def execute_tool_calls_concurrently(tool_calls):
    """并发执行一轮的多个工具调用，返回 {tool_call_id: result}。"""
    if len(tool_calls) > MAX_PARALLEL_CALLS:
        return {
            call.id: {'ok': False, 'error': 'too_many_tool_calls'}
            for call in tool_calls
        }
    executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS)
    future_to_call = {
        executor.submit(execute_tool_call, call): call
        for call in tool_calls
    }
    done, not_done = wait(future_to_call, timeout=TOOL_BATCH_TIMEOUT)
    results_by_id = {}
    for future in done:
        call = future_to_call[future]
        try:
            results_by_id[call.id] = json.loads(future.result())
        except Exception:
            results_by_id[call.id] = {'ok': False, 'error': 'too_failed'}
    for future in not_done:
        call = future_to_call[future]
        future.cancel()
        results_by_id[call.id] = {'ok': False, 'error': 'batch_wait_timeout'}
    executor.shutdown(wait=False, cancel_futures=True)
    return results_by_id


# ==================== 多轮调用闭环 ====================
def run(user_text, parallel=False, concurrent=False):
    """跑一次多工具调用闭环，返回最终回答。"""
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': user_text},
    ]

    for _ in range(MAX_ROUNDS):
        resopnse = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice='auto',
            parallel_tool_calls=parallel
        )

        assistant_message = resopnse.choices[0].message
        messages.append(assistant_message.model_dump(exclude_none=True))

        tool_calls = assistant_message.tool_calls or []
        if not tool_calls:
            if not assistant_message.content:
                raise RuntimeError('模型没有返回工具调用或最终回答')
            return assistant_message.content

        if concurrent and len(tool_calls) > 1:
            # 受控并发：一次执行本轮所有调用
            results_by_id = execute_tool_calls_concurrently(tool_calls)
            for tool_call in tool_calls:
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tool_call.id,
                    'content': json.dumps(
                        results_by_id[tool_call.id],
                        ensure_ascii=False
                    )
                })

        else:
            #顺序执行
            for tool_call in tool_calls:
                result = execute_tool_call(tool_call)
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tool_call.id,
                    'content': json.dumps(result, ensure_ascii=False)
                })
    raise RuntimeError('处理轮数超过上限，已停止')


# ==================== 主程序 ====================
def main():
    while True:
        user_text = input('你: ').strip()
        if user_text.lower() in {'exit', 'quit'}:
            print('会话结束')
            break
        if not user_text:
            print('请输入内容')
            continue
        try:
            answer = run(user_text)
            print(f"助手：{answer}")
        except Exception as error:
            print(f"调用失败：{type(error).__name__}: {error}")

if __name__ == "__main__":
    main()

























































