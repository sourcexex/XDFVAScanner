# xdflib（内置副本）

本目录是 **XDFLib 0.1.0** 的源码副本，随 XDFVAScanner 一起分发，
目的是让本项目只依赖公开的 PyPI 包（`requests`、`cryptography`）即可运行，
不再需要克隆/安装外部的 `XDFLib` 目录。

| 项 | 值 |
|---|---|
| 上游 | XDFLib — XDF Pad communication protocol library 0.1.0 |
| 许可 | MIT（全文见同目录 `LICENSE`） |
| 引入日期 | 2026-11-20 |
| 相对上游的改动 | 仅 `im/bridge.py` 中 Node 桥接目录的定位逻辑与提示文案（见下） |

## 升级方式

用上游 `XDFLib/src/xdflib/` 整体覆盖本目录即可，然后重新应用下面的改动。

## 本地改动

1. `im/bridge.py` — 桥接脚本目录不再写死为源码树相对路径，而是按
   `XDFLIB_BRIDGE_DIR` 环境变量 → 仓库根 `bridge/` → 包内 `bridge/` → 当前工作目录 `bridge/`
   的顺序查找，安装成包后也能找到（对应仓库根目录的 `bridge/bridge.cjs`）。
2. `im/bridge.py` — “Bridge 脚本未找到”的提示文案改为指向本项目 `bridge/` 目录。

## 可选依赖

- IM Bridge 模式需要 Node.js + `@tencentcloud/chat`（公开 npm 包）：
  在 `bridge/` 目录执行 `npm install`。扫描器本身不使用 IM，可忽略。
- `agora.py` 只做 Token 生成与频道查询，不强制依赖 `agora-python-sdk2`。
