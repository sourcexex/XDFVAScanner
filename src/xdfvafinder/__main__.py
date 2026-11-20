"""``python -m xdfvafinder``：默认进入账号扫描器。"""

import sys

from .scanner import main

if __name__ == "__main__":
    sys.exit(main())
