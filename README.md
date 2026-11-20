# XDFVAFinder — XDF 账号安全扫描器

针对 XDF 平台账号体系的**授权安全测试工具**，用于发现测试账号段中存在的弱口令 / 可登录账号问题。

> ⚠️ **合规声明**
> 本项目仅用于 XDF 官方授权的安全测试，以及测试环境（`--env test`）下的账号巡检。
> 请勿对生产环境或未经授权的账号进行扫描，否则可能触犯相关法律法规。

## 功能

- **账号扫描** (`scanner.py`) — 按号段批量遍历，检测可登录的账号，并自动拉取该账号下的学员信息
- **登录调试** (`debug_login.py`) — 对单个账号发起登录请求，打印完整的请求/响应细节，用于协议调试与排查

## 环境要求

- Python **>= 3.13**
- 第三方依赖（全部来自公开 PyPI）：`requests`、`tqdm`、`cryptography`
- 协议库 `xdflib`：**已内置在 `src/xdflib/`**，随本项目一起安装，不需要再下载或安装外部目录

## 安装

```bash
# 推荐：用 uv 建虚拟环境并装好依赖 + 本项目
uv sync

# 或者用 pip（会以可编辑模式安装本项目，包含内置的 xdflib）
pip install -e .
```

安装后可以直接使用命令行入口 `xdfvafinder`、`xdf-debug-login`。

> 协议库源码已经在 `src/xdflib/`，脚本里指向外部目录的 `sys.path` 回退逻辑也已删除，
> 所以不需要再单独安装外部协议库。

## 快速开始

```bash
# 扫描测试环境的小范围（推荐先用这个验证）
uv run python scanner.py --start 0 --end 99 --env test

# 单账号登录调试
uv run python debug_login.py -m 14400000444 -p XdFopt00000 --env test
```

装好之后（`uv sync` / `pip install -e .`）也可以直接用命令行入口：

```bash
uv run xdfvafinder --start 0 --end 99 --env test
uv run xdf-debug-login -m 14400000444 -p XdFopt00000 --env test
```

以 `python -m` 方式运行同样有效：`python -m xdfvafinder`、`python -m xdfvafinder.scanner`、
`python -m xdfvafinder.debug_login`。根目录的 `scanner.py` / `debug_login.py` 只是兼容入口，
真正的代码在 `src/xdfvafinder/`。

## scanner.py 用法

遍历指定范围内的号码，尝试登录并记录有效账号。

### 账号生成规则

| 项 | 格式 | 示例（digits=12345） |
|---|---|---|
| 手机号 | `144{digits:05d}444` | `14412345444` |
| 密码 | `XdFopt{digits:05d}` | `XdFopt12345` |

> `digits` 为 0 ~ 99999 的五位数字。

### 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--start` | `0` | 起始数字（0 ~ 99999） |
| `--end` | `99999` | 结束数字（0 ~ 99999，需 >= `--start`） |
| `--threads` | `3` | 并发线程数（>= 1） |
| `--delay` | `0.5` | 请求间隔秒数（>= 0，跨线程限速） |
| `--resume` | `false` | 从断点恢复扫描 |
| `--env` | `prod` | 环境：`test` 或 `prod`（默认 prod，**测试请务必显式指定 `test`**） |
| `--output` | `valid_accounts.txt` | 结果输出文件 |
| `--checkpoint` | `scan_progress.json` | 断点文件路径 |
| `--log-file` | `scan.log` | 日志文件路径 |
| `--incremental` | `false` | 增量扫描：跳过上次确认不可用的号码 |
| `--cache` | `scan_cache.json` | 增量缓存文件 |
| `--cache-ttl` | `30` | 增量缓存有效期（天），`0` 表示永不过期 |
| `--verbose` / `-v` | `false` | 控制台输出详细日志 |

### 示例

```bash
# 测试小范围（TEST 环境）
uv run python scanner.py --start 0 --end 99 --env test

# 测试小范围 + 详细日志
uv run python scanner.py --start 0 --end 99 --env test --verbose

# 高并发快速模式
uv run python scanner.py --threads 8 --delay 0.1

# 从断点恢复（中断后继续）
uv run python scanner.py --resume
```

### 行为说明

- **限速**：所有线程共享一个请求节奏，相邻请求至少间隔 `--delay` 秒，避免请求过密
- **并发**：线程池同时在途的任务数有上限（`4 × threads`），内存占用不随号段长度增长，`Ctrl+C` 也能立即停止派发
- **日志**：所有信息写入 `scan.log`（控制台默认只显示警告和错误，加 `-v` 显示全部）
- **统计**：`--resume` 时会接续断点里记录的总数与有效数，汇总里是累计值
- **增量**：`--incremental` 跳过缓存中上次确认不可用的号码，汇总里会单独显示跳过数量

### 断点与中断恢复

每连续扫描 100 个号码自动保存一次 `scan_progress.json`；`Ctrl+C` / `SIGTERM` 会优雅退出，
把**当前连续水位**写入断点并以退出码 `130` 结束，下次加 `--resume` 从水位之后继续。

> 断点记录的是"从起点起连续扫码到哪一位"，而不是"最后完成的那一个"。
> 多线程下任务完成顺序是乱序的，这样可以保证 `--resume` 不会跳过尚未扫完的号码
> （最多重扫少量正在途中的号码，不会漏扫）。

三个产物路径都可以自定义，例如把结果统一放到 `output/` 目录：

```bash
uv run python scanner.py --output output/valid_accounts.txt \
    --checkpoint output/scan_progress.json --log-file output/scan.log --resume
```

### 增量扫描

`--incremental` 会读取一份"不可用账号缓存"，把上次已经确认不可用的号码直接跳过，
只请求可能有效或还没扫过的号码：

```bash
# 第一次（没有缓存）：全量扫描，同时记录确认不可用的号码
uv run python scanner.py --start 0 --end 99999 --env test --incremental

# 之后：自动跳过上次不可用的，只复查已知有效 / 新增的号码
uv run python scanner.py --start 0 --end 99999 --env test --incremental
```

- 缓存文件默认 `scan_cache.json`（`--cache` 可改），内容是 `号码 -> 确认不可用时间`
- 只有**明确被拒绝**的账号才进缓存：网络错误、任务异常、中断都不算，下次会重试
- 条目默认 30 天过期（`--cache-ttl 30`），过期后重新检查；`--cache-ttl 0` 表示永不过期
- 已知有效的账号**不会**被跳过，每次增量都会重新登录确认一次（数量很少，成本很低）
- 被跳过的号码同样计入断点水位，所以 `--incremental --resume` 可以一起用，不会倒回去重扫
- 缓存里只有号码和时间戳，不含密码；仍建议和结果文件一样妥善保管
- 汇总里会多两行：`跳过（上次不可用）` 和 `增量缓存` 的条目数

典型效果：首次全量 10 万号后，第二周增量只剩"历史有效账号 + 新号段"量级的请求。

### 输出文件格式

`valid_accounts.txt`（管道符分隔，固定 9 列）：

```
手机号|密码|u2_user_id|学员ID|学员编号|姓名|年级|学校ID|学校名
```

账号下没有学员时，其余列留空（例如 `14400000444|XdFopt00000|u2-xxx||||||`）。

## debug_login.py 用法

对单个账号发起登录请求，打印完整调试信息（加密后的用户名/密码、签名头、HTTP 状态码、原始 JSON 响应、
auth.py 判定结果、学员列表等）。

```bash
uv run python debug_login.py -m 13800138000 -p mypassword --env prod
uv run python debug_login.py -m 13800138000 -p mypassword --env test
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--mobile` / `-m` | 必填 | 手机号 |
| `--password` / `-p` | 必填 | 密码 |
| `--env` | `prod` | 环境：`test` 或 `prod` |
| `--timeout` | `15` | 单次请求超时秒数 |

## 退出码

| 退出码 | 含义 |
|---|---|
| `0` | 正常结束（或断点已覆盖到 `--end`，无需扫描） |
| `1` | `debug_login` 请求失败（网络异常） |
| `2` | 命令行参数错误 |
| `130` | 扫描被 `Ctrl+C` / `SIGTERM` 中断（断点已保存） |

## 生成的文件与数据安全

| 文件 | 说明 |
|---|---|
| `valid_accounts.txt` | 有效账号及学员信息（**含明文密码**） |
| `scan_progress.json` | 断点进度（供 `--resume` 使用） |
| `scan.log` | 运行日志（**含明文密码，`-v` 时更多细节**） |

以上文件都已写入 `.gitignore`。由于内容包含账号凭据，请只在授权环境保存，
必要时限制目录权限（例如 `chmod 600` / 单独的测试机）。

## GitHub Actions

仓库里带了三份工作流，手动扫描和每周定时扫描共用一个可复用流程：

| 工作流 | 文件 | 触发方式 | 默认行为 |
|---|---|---|---|
| Scan (manual) | `.github/workflows/scan-manual.yml` | 手动 `Run workflow` | `test` 环境、全号段、每片 10000 个号码 |
| Scan (weekly) | `.github/workflows/scan-weekly.yml` | 每周一 01:00 UTC + 手动 | 读仓库变量，缺省 `test` 环境 |
| Scan (reusable) | `.github/workflows/scan-run.yml` | 被上面两个调用 | plan → scan → report |

执行流程：`plan` 校验参数并把号段切成若干片 → `scan` 用矩阵并发跑分片（每个 job 独立扫描，
受 6 小时 job 上限约束）→ `report` 合并去重、生成 `scan_summary.json`，并在 run 页面写入汇总表。

### 手动扫描

`Actions → Scan (manual) → Run workflow`，可填：

| 输入 | 说明 |
|---|---|
| `env` | `test` / `prod` |
| `confirm_prod` | `env=prod` 时**必须勾选**（确认已获 XDF 授权），否则 plan 阶段直接失败 |
| `start` / `end` | 号段（0~99999） |
| `chunk_size` | 每个 job 负责的号码数 |
| `threads` / `delay` | 单 job 的线程数与请求间隔（秒） |
| `max_parallel` | 同时运行的 job 数（1~8） |
| `verbose` | 输出详细日志 |

### 每周自动扫描

- 时间：`0 1 * * 1`，即**每周一 01:00 UTC / 北京时间 09:00**
- 参数取自仓库变量（`Settings → Secrets and variables → Actions → Variables`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `SCAN_ENV` | `test` | 扫描环境 |
| `SCAN_START` / `SCAN_END` | `0` / `99999` | 号段 |
| `SCAN_CHUNK_SIZE` | `10000` | 每片号码数 |
| `SCAN_THREADS` | `3` | 单 job 线程数 |
| `SCAN_DELAY` | `0.5` | 单 job 请求间隔（秒） |
| `SCAN_MAX_PARALLEL` | `2` | 并发 job 数（1~8） |
| `SCAN_CACHE_TTL` | `30` | 增量缓存有效期（天），`0` 表示永不过期 |
| `SCAN_ALLOW_PROD` | 未设置 | 设为 `true` 才允许每周扫 `prod` |

- 增量扫描默认开启：每个分片先从上一次运行的 Actions Cache 恢复 `scan_cache.json`，
  扫完由合并 job 汇总、保存为新的缓存。**首次运行等于全量**，之后会跳过已知不可用的号码，快很多
- 想强制全量复查：手动触发时把 `incremental` 设为 `false`，或到仓库 Settings → Actions → Caches 删掉缓存

> `schedule` 只在**默认分支**上生效：改完工作流要先推送到默认分支，定时任务才会开始计时。
> 另外公开仓库若连续 60 天没有任何提交，GitHub 会自动暂停定时工作流（可在 Actions 页面手动启用）。
> 同一环境的扫描会串行排队（`concurrency`），手动触发不会和定时任务叠在一起。

### 产物与配额

- 每个分片：`scan-chunk-<start>-<end>-<attempt>` 产物（14 天），含结果文件、断点、日志和增量缓存片段
- 合并结果：`scan-result-<attempt>` 产物（30 天），含 `valid_accounts_merged.txt`、`valid_accounts_merged.csv`、
  `scan_summary.json`、合并后的 `scan_cache.json`（名称带 attempt 后缀，重跑不会和上一次冲突）
- 单文件 CSV：`scan-csv-<attempt>` 产物（30 天），只有 `valid_accounts_merged.csv` 一个文件，
  表头是中文列名，UTF-8 BOM 编码，Excel 双击打开不乱码
- 单个 job 超时 350 分钟；建议 `chunk_size × delay` 控制在 4 小时以内
- 运行分钟粗算：`号码数 × delay / 60`。全量 10 万号 + `delay=0.5` ≈ 833 分钟/次；
  私有仓库免费额度是 2000 分钟/月，建议调小号段、`SCAN_DELAY`（例如 `0.2`）或降低频率
- runner 是一次性的，`--resume` 在 CI 里没有意义：断点只在单个 job 内消解在途号码，
  跨 job / 跨运行不会续扫，失败就重跑那一片

> ⚠️ artifact 里同样是**明文密码**。请收紧仓库可见性、按需缩短保留期，并在每次定时扫描前
> 确认授权仍然有效；`prod` 默认不允许自动扫描。

## 项目结构

```
XDFVAScanner/
├── scanner.py              # 兼容入口 → src/xdfvafinder/scanner.py
├── debug_login.py          # 兼容入口 → src/xdfvafinder/debug_login.py
├── .github/workflows/      # 手动扫描 / 每周定时扫描 / 可复用扫描流程
├── src/
│   ├── xdfvafinder/        # 本项目代码
│   │   ├── scanner.py      #   扫描主流程（并发、限速、进度）
│   │   ├── debug_login.py  #   单账号抓包式调试
│   │   ├── checkpoint.py   #   断点读写 + 连续水位
│   │   ├── cache.py        #   增量缓存（记住上次不可用的号码）
│   │   ├── storage.py      #   结果文件写入（线程安全）
│   │   ├── env.py          #   test/prod → xdflib 环境配置
│   │   └── __main__.py     #   python -m xdfvafinder
│   └── xdflib/             # 内置协议库（登录、加密签名、IM、Agora、白板）
│       ├── auth.py         #   XDFAuthClient — 登录 / 学员列表 / IM 凭证
│       ├── crypto.py       #   AES、HMAC-SHA1、sdkSign
│       ├── http.py         #   带签名头的 POST / GET
│       ├── im/             #   腾讯 IM（REST / Bridge、消息编解码）
│       ├── agora.py        #   Agora RTC Token
│       └── whiteboard.py   #   白板信令
├── bridge/                 # xdflib IM 的 Node 桥接（可选，需 npm install）
├── tests/                  # 离线单元测试（加密、消息、断点、结果写入、扫描流程）
├── pyproject.toml          # 依赖、打包、pytest 与 ruff 配置
└── uv.lock
```

## 内置协议库 xdflib

`src/xdflib/` 是协议库 XDFLib 0.1.0 的源码副本（MIT，许可全文见 `src/xdflib/LICENSE`）。
之所以内置，是为了让本项目 **只依赖公开的 PyPI 包**即可运行：

- 运行时依赖只有 `requests` 和 `cryptography`，两者都在 PyPI 上
- 扫描器只用到 `xdflib.auth` / `xdflib.crypto` / `xdflib.http` / `xdflib.models` / `xdflib.errors`
- 其余模块（IM / Agora / 白板）保留完整能力，供后续扩展使用，不引入额外强制依赖
- IM 的 Bridge 模式额外需要 Node.js 和公开 npm 包 `@tencentcloud/chat`（在 `bridge/` 执行 `npm install`）；扫描器不使用，可忽略

来源、改动记录和升级方式见 `src/xdflib/VENDORED.md`。

## 开发

```bash
uv sync                          # 安装依赖（含 dev 组：pytest、ruff）
uv run pytest                    # 运行测试（全部离线，不产生真实请求）
uv run ruff check                # lint（内置的 src/xdflib 已排除）
uv run ruff format --check       # 格式检查
```

提交前建议依次跑一遍 `ruff check`、`ruff format --check`、`pytest`。

## 常见问题

**Q: 报错 `ModuleNotFoundError: No module named 'xdflib'`**
在项目根目录执行 `uv sync`（或 `pip install -e .`），然后用 `uv run python scanner.py ...` 运行；
内置的 `src/xdflib` 会随本项目一起安装，不需要外部 `XDFLib` 目录。

**Q: 之前外置的 XDFLib 目录还要保留吗**
不用。原先 `pyproject.toml` 里的 `[tool.uv.sources]` 路径依赖和脚本里的 `sys.path` 回退都已移除，
旧目录可以直接删除。

**Q: 断点文件损坏怎么办**
扫描器检测到 `scan_progress.json` 无法解析或字段缺失时会忽略它（记一条警告）并从起始位置重新开始。

**Q: 中断后如何继续**
直接运行 `python scanner.py --resume`，会从断点记录的连续水位之后继续扫描。

**Q: 扫描很慢 / 想加快**
`--delay` 是跨线程的全局请求间隔，调小它（例如 `--delay 0.1`）比单纯加线程更有效；
但请遵守授权范围与对方接口的承受能力。
