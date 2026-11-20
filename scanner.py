#!/usr/bin/env python3
"""兼容入口：等价于 ``python -m xdfvafinder.scanner``。

真正的实现在 ``src/xdfvafinder/scanner.py``，这里只保留 ``python scanner.py ...``
这种老用法。未安装本项目时会把 ``src`` 加入 ``sys.path``。
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from xdfvafinder.scanner import main  # noqa: E402  (需先修正 sys.path)

if __name__ == "__main__":
    sys.exit(main())
