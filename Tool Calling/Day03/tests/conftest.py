import sys
from pathlib import Path

# 保证从仓库根目录运行 pytest 时也能导入 Day03 下的模块
DAY03_DIR = Path(__file__).resolve().parents[1]
if str(DAY03_DIR) not in sys.path:
    sys.path.insert(0, str(DAY03_DIR))
