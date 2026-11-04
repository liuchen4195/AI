import logging
import time
import uuid

#日志记录 + 请求耗时统计 + trace_id 追踪的模块，设计目标是只记元数据、不记原始输入和完整输出（保护隐私）

logging.basicConfig(
    filename='llm_app.log', #日志写到文件
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s', #每条日志的格式：时间（时间戳）、级别、消息
    encoding='utf-8'
)

#接收 trace_id（唯一ID）、模型名、状态、开始时间、结果字典
def log_result(trace_id, model_name, status, started_at, result):
    """ 只记录元数据，不接收原始输入和完整输出。"""
    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    logging.info(
        'trace_id=%s model=%s status=%s elapsed_ms=%s',
        'output_chars=%s error_type=%s',
        trace_id,
        model_name,
        status,
        elapsed_ms,
        len(result.get('text', '')),
        result.get('error_type')
    )

trace_id = uuid.uuid4().hex[:12]
started_at = time.perf_counter()
































































