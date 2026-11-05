import os
import sys
from pathlib import Path

# 保证从仓库根目录运行 pytest 时也能导入 Day03 下的模块
DAY03_DIR = Path(__file__).resolve().parents[1]
if str(DAY03_DIR) not in sys.path:
    sys.path.insert(0, str(DAY03_DIR))

# app/service 在导入时校验配置；测试使用占位值，不会发起真实请求
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("BASE_URL", "http://127.0.0.1:1/v1")
