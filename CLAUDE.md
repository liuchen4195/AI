# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库定位

大模型应用开发课程的学习仓库：按课程天/主题组织的练习脚本与 Jupyter notebook，**不是可安装的 Python 包**。代码注释、Prompt、文件名大量使用中文，新增代码沿用中文注释与中文错误提示。

## 环境与运行

- 依赖装在根目录 `.venv`（Windows venv，解释器为 `.venv/Scripts/python.exe`）；依赖清单见根目录 `requirements.txt`（openai、ollama、pydantic、python-dotenv、tiktoken、httpx）。
- 配置在根目录 `.env`（已 gitignore，无 .env.example）：
  - `OPENAI_API_KEY` / `OPENAI_MODEL` / `BASE_URL` — 云端模型走 OpenAI SDK，`BASE_URL` 可指向中转服务；缺任一则脚本 `raise RuntimeError`。
  - `OLLAMA_MODEL` — 本地模型走 `ollama` Python SDK（`from ollama import chat`）。
- 脚本用 `load_dotenv()` 读 `.env`，并约定**从仓库根目录运行**（docstring 里也如此要求），路径含空格和中文时必须加引号：

  ```bash
  python "6.Tool Calling与阶段项目/examples/day01_room_assistant.py"
  ```

- 例外：`Tool Calling/Day03` 内部用相对路径 `data/history.json`，需先 `cd "Tool Calling/Day03"` 再 `python main.py`。

## 测试

两类测试都在离线假模型（`FakeClient`）下运行，不访问网络、不读 `.env`：

- 独立脚本，直接 `python` 运行并打印 PASS/FAIL：
  `python "6.Tool Calling与阶段项目/examples/day01_room_assistant_test.py"`
- pytest 风格（根目录有 `.pytest_cache`，从根目录运行）：
  `python -m pytest "Tool Calling/Day02/完成多工具调用闭环/test_validation.py" -v`

无 lint/CI 配置。

## 课程主线（目录即课程阶段）

1. `AI全景认知/` — 机器学习/深度学习/NLP 概念 notebook（Day01–05），数据在 `data/`，产出在 `outputs/`。
2. `LLM/` — 模型调用基础：Day01 token 化 → Day02 云端对话 → Day03 Ollama 本地对话 → Day04 多轮对话 → Day05 流式/异常/日志 → Day06 Prompt 与 Pydantic 结构化输出；`综合实战/` 是集成小应用。`session.json` 是对话历史的持久化文件。
3. `Tool Calling/` 与 `6.Tool Calling与阶段项目/` — 工具调用：Day01 基础调用与安全执行 → Day02 受控调用、参数校验、工具选择 → Day03 完整项目（下述）。

`111/` 是随意练习目录，不属于主线。

## 参考架构：Tool Calling/Day03 天气助手

本仓库最完整的应用，读多文件才能理解的分工：

- `main.py` — 交互入口：SYSTEM_PROMPT + `/history /clear /help /exit` 命令 + 耗时统计
- `model.py` — Pydantic 参数模型 + 工具合同（`strict: True` 的 JSON Schema），只描述给模型看的契约
- `service.py` — 受控循环：`trim()` 裁剪历史（保留 system，按轮数截断）→ 最多 10 轮 → `asyncio.gather` 并行执行多个工具
- `tools.py` — aiohttp 调用 open-meteo 免费 API（地理编码/天气/空气质量）+ `tools_map` 注册表（名字 → {函数, 参数模型}）
- `history.py` / `tracks.py` — 会话历史与调用轨迹的 JSON 持久化（`ensure_ascii=False`，容错加载）

## 贯穿全部示例的关键约定

- **工具合同与执行分离**：Pydantic 模型经 `model_json_schema()` 生成模型侧合同；执行侧用注册表（`tools_map` / `TOOL_REGISTRY`）按名字查函数，两层必须一致。
- **工具执行安全**：模型输出按不可信输入处理——白名单 → JSON 解析（禁 `eval`）→ 字段/类型/业务校验 → 异常兜底为稳定错误码（`tool_not_allowed` / `invalid_json` / `invalid_arguments` / `tool_failed`），结果以 `{"ok": ..., "error": ...}` 回传模型。
- **受控循环与消息顺序**：最多 N 轮（`MAX_ROUNDS`）防死循环；先追加含 `tool_calls` 的 assistant 消息，再追加 `role=tool` 消息，且 `tool_call_id` 必须复用模型返回的原始 ID。
- **结果只来自工具**：各 SYSTEM_PROMPT 普遍要求模型不得凭记忆编造坐标、天气等数据，候选不明确时反问用户。
