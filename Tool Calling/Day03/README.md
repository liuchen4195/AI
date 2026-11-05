# Day03 天气查询助手

带 Tool Calling 的天气/空气质量/会议室助手，包含命令行入口和网页入口。网页左侧连续对话，右侧展示本轮模型请求与工具调用轨迹。

## 功能

- 城市天气（open-meteo）
- 城市空气质量（open-meteo）
- 会议室信息（本地 `data/meeting_rooms.json`）
- 多轮对话、并行工具调用、参数校验与工具白名单
- 本轮轨迹：模型请求次数、工具轮次、串并行、工具参数/结果、开始/结束时间、耗时、Token 与停止原因
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
- 响应不包含 system 提示词、历史消息、本机路径或密钥

前端交互与轨迹渲染使用 Chrome CDP 做过手工自动化验证，详见 `验收记录.md`。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| POST | `/api/chat` | `{ "question": "北京天气怎么样？" }`，返回 `{ok, answer, trace}` |
| POST | `/api/clear` | 清空当前会话 |

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
├── tools.py               # 工具实现与白名单
├── static/                # 页面、样式、交互脚本
├── deploy/                # Caddy / systemd / 生产环境变量模板
├── tests/                 # pytest 测试
├── data/                  # 课程历史、轨迹、会议室数据（运行时生成/读取）
├── 历史持久化设计.md        # Web 历史/轨迹持久化扩展设计
├── 开发设计方案.md
├── 验收记录.md
└── 项目总结.md
```

## 当前范围与限制

- 单用户、进程内单会话；服务重启后会话清空；
- 不提供登录、云端同步、轨迹历史列表；
- 所有时间与 Token 均来自真实运行记录，缺失时分别显示“未记录/未返回”；
- 步骤 10 的工具轮次/调用数量/城市数量限额，以及步骤 11 的 CSP 等安全响应头尚未实现；
- 当前环境未配置模型密钥，自动化测试使用模拟模型响应；open-meteo 与会议室工具已真实调用验证。

更完整的设计与步骤状态见 `开发设计方案.md`。
