# Day03 天气查询助手

带 Tool Calling 的天气/空气质量/会议室助手，包含命令行入口和网页入口。网页左侧连续对话，右侧展示本轮或历史轮次的模型请求与工具调用轨迹。

## 功能

- 城市天气（open-meteo）
- 城市空气质量（open-meteo）
- 会议室信息（本地 `data/meeting_rooms.json`）
- 多轮对话、并行工具调用、参数校验与工具白名单
- 轨迹：模型请求次数、工具轮次、串并行、工具参数/结果、开始/结束时间、耗时、Token 与停止原因
- 历史持久化：每轮问题和完整轨迹保存到 `data/web_sessions/`，刷新浏览器或重启服务后可恢复
- 每轮助手消息提供“查看轨迹”，可切换历史轮次并回到最新
- 失败与部分成功状态、错误脱敏、清空对话、移动端单列布局

## 环境要求

- Python 3.10+
- 可访问 open-meteo 与所选 OpenAI 兼容模型服务

## 安装

```bash
cd "Day03"
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

复制环境变量模板并填写：

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

```dotenv
OPENAI_API_KEY=你的密钥
OPENAI_MODEL=你的模型名
BASE_URL=你的 OpenAI 兼容服务地址
```

Web 历史默认保存在 `data/web_sessions/`，可用环境变量覆盖：

```dotenv
WEB_HISTORY_DIR=/opt/weather/data/web_sessions
```

## 运行

### Web 页面

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

或：

```bash
python app.py
```

浏览器打开 `http://127.0.0.1:8000`。

部署到公网域名（云服务器 + Caddy + HTTPS + 访问密码）的模板见 `deploy/` 目录。

Web 历史记录与轨迹持久化设计见 [`历史持久化设计.md`](历史持久化设计.md)。

### 命令行

```bash
python main.py
```

CLI 支持：

- `/help`：帮助
- `/history`：查看历史
- `/clear`：清空历史
- `/rooms`：查看会议室

## 测试

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

当前测试覆盖：

- 轨迹采集、计时、Token 缺失/部分/累计、错误分类与脱敏
- 服务层成功、工具失败、模型异常、最大轮次
- 健康检查、对话、清空、输入校验、忙碌保护、额外字段注入
- Web 历史文件、原子写、损坏文件隔离、会话隔离、刷新/重启恢复、历史轨迹详情
- 响应和历史文件不包含 system 提示词、密钥、本机路径

前端交互与轨迹渲染使用 Chrome CDP 做过手工自动化验证，详见 `验收记录.md`。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| POST | `/api/chat` | `{ "question": "北京天气怎么样？" }`，返回 `{ok, answer, trace, turn_id, history_saved}` |
| GET | `/api/history` | 返回当前浏览器会话的轮次摘要 |
| GET | `/api/history/{turn_id}` | 返回该轮完整轨迹 |
| POST | `/api/clear` | 清空当前会话及本地历史 |

- 每个浏览器通过 HttpOnly Cookie `weather_session_id` 隔离会话；
- 问答处理中返回 409；
- 空白问题返回 400；
- 业务失败仍返回 200，并附带失败轨迹；
- 客户端只能提交 `question`，不能注入 system 或历史消息。

## 目录

```text
Day03/
├── app.py                 # FastAPI 入口、会话、接口
├── main.py                # CLI 入口
├── prompt.py              # 共用系统提示词
├── model.py               # 工具合同
├── service.py             # Tool Calling 受控循环
├── trace.py               # 轨迹采集与错误脱敏
├── web_history.py         # Web 会话文件、Cookie 会话与历史存储
├── tools.py               # 工具实现与白名单
├── static/                # 页面、样式、交互脚本
├── deploy/                # Caddy / systemd / 生产环境变量模板
├── tests/                 # pytest 测试
├── data/                  # 会议室数据、CLI 历史、Web 会话历史（运行时生成/读取）
├── 历史持久化设计.md        # Web 历史/轨迹持久化扩展设计
├── 开发设计方案.md
├── 验收记录.md
└── 项目总结.md
```

## 当前范围与限制

- 每个浏览器独立会话；历史保存在本地 `data/web_sessions/`，服务重启后仍可恢复；
- 不提供账号登录、云端同步；公开部署建议使用 `deploy/` 中的 Caddy Basic Auth + HTTPS；
- 固定单 worker，因为会话在进程缓存中；多 worker 需要文件锁或 Redis；
- 所有时间与 Token 均来自真实运行记录，缺失时分别显示“未记录/未返回”；
- 步骤 10 的工具轮次/调用数量/城市数量限额，以及步骤 11 的 CSP 等安全响应头尚未实现；
- 当前环境未配置模型密钥，自动化测试使用模拟模型响应；open-meteo 与会议室工具已真实调用验证。

更完整的设计与步骤状态见 `开发设计方案.md`。
