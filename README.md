# 樱桃与小番茄贮藏预测系统

基于 Flask、LangChain 和 SQLite 的双品类预测应用。樱桃保留原有温度/硬度模型；小番茄使用独立实验数据与阈值插值方法。

**当前运行配置：`AUTH_ENABLED=False`、`HISTORY_ENABLED=False`。无需登录，不保存预测历史。下方账号/历史功能描述为保留代码能力，并非当前已开放功能。小番茄结果不写入樱桃历史表。

## 功能

- 用户注册、登录和退出
- 密码哈希存储与登录访问控制
- 三次多项式回归货架期预测
- 硅基流动 LLM 结构化预测（需要配置 API Key）
- 自动保存每位用户的预测历史
- 最近 20 次货架期趋势图
- 最近 100 条记录的风险分布和统计指标
- 历史记录表格
- 一键清除当前用户的全部预测历史
- 将当前用户的全部历史记录导出为 `.xlsx`

## 预测方法

### 多项式回归

```text
L = -0.00177778*T^3 + 0.0952381*T^2 - 2.03175*T + 24.2381
```

其中 `T` 是贮藏温度（℃），`L` 是基础货架期（天）。系统保留原始多项式和硬度修正逻辑，并使用温度—硬度二维对数空间高斯径向基校准，使“0 ℃、手持硬度 70 = 37 天”“5 ℃、手持硬度 70 = 25 天”和“25 ℃、手持硬度 60 = 2 天”三个参考点精确命中。10、15、20、25 ℃下还设置了硬度 70 的温度平滑控制点，以避免相邻温度出现不合理跳变。

### LLM 结构化判断

通过 LangChain 调用硅基流动的 OpenAI-compatible API，默认模型为 `Qwen/Qwen2.5-7B-Instruct`。模型输出经过 JSON 提取和 Pydantic 结构校验。

## 安装

```powershell
cd C:\Users\liuzhen\Desktop\材料\code\meizao-cherry-shelf-life
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 环境变量

在项目根目录创建或修改 `.env`：

```text
SILICONFLOW_API_KEY=你的硅基流动_API_Key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=Qwen/Qwen2.5-7B-Instruct
FLASK_SECRET_KEY=请替换为随机且保密的字符串
```

如果没有设置 `FLASK_SECRET_KEY`，开发环境会自动在 `instance/.secret_key` 中生成并保存随机密钥。

## 完全独立的单文件终端版

如果需要脱离当前 Web 项目单独使用，请复制下面的目录：

```text
standalone_cli/
```

其中 `cherry_shelf_life_cli.py` 已包含完整预测模型，不会导入本项目的 `src` 目录，也不需要任何第三方包：

```powershell
cd standalone_cli
python cherry_shelf_life_cli.py 10 60 --details
```

也可以把这一个 `.py` 文件单独复制到其他电脑或目录运行。

## 终端版预测程序

核心预测算法已抽离到不依赖 Flask、LangChain 或 Pydantic 的纯 Python 模块：

```text
src/core_predictor.py
```

直接进入交互式终端：

```powershell
python predict_cli.py
```

也可以在命令中直接提供“温度”和“硬度”：

```powershell
python predict_cli.py 10 60
```

显示计算明细：

```powershell
python predict_cli.py 10 60 --details
```

输出 JSON：

```powershell
python predict_cli.py 10 60 --json
```

Windows 下也可以双击：

```text
run_predict_cli.bat
```

终端版只使用 Python 标准库，不需要启动网页、数据库或登录功能。Web 应用与终端程序调用同一个核心预测模块，保证计算结果一致。

## 启动 Web 应用

```powershell
python app.py
```

浏览器访问：

```text
http://127.0.0.1:5000
```

当前无需注册账号。SQLite 数据库会自动创建在：

```text
instance/meizao.sqlite3
```

## 页面功能

1. 注册或登录个人账号。
2. 选择 0、5、10、15、20 或 25 ℃。
3. 输入 60-90 范围的手持式硬度计读数。
4. 点击“计算并保存预测”。
5. 在页面下方查看趋势图、风险分布和历史记录。
6. 点击“导出 Excel”下载当前账号的全部预测历史。

## 接口

| 方法 | 路径 | 说明 | 是否需要登录 |
| --- | --- | --- | --- |
| GET/POST | `/register` | 注册账号 | 否 |
| GET/POST | `/login` | 用户登录 | 否 |
| POST | `/logout` | 退出登录 | 是 |
| GET | `/` | 预测工作台 | 是 |
| POST | `/predict` | 执行预测并保存历史 | 是 |
| GET | `/api/history` | 获取当前用户历史记录 | 是 |
| GET | `/history/export` | 导出当前用户历史 Excel | 是 |
| POST | `/history/clear` | 清除当前用户全部历史记录 | 是 |
| GET | `/health` | 健康检查 | 否 |
| GET | `/methods` | 查看预测方法 | 否 |

浏览器页面的 POST 请求带有 CSRF 校验。如果使用脚本直接调用 `/predict`，需要先 GET 页面取得会话 Cookie 和 meta 中的 CSRF token，再携带 Cookie 和 `X-CSRF-Token` 请求头；当前无需登录。

## 数据说明

- 每个用户只能查看和导出自己的预测历史。
- 密码只保存哈希值，不保存明文。
- 历史数据保存在本地 SQLite 数据库中。
- 部署到 HTTPS 环境时，建议将 Flask 的 `SESSION_COOKIE_SECURE` 配置为 `True`。


## 小番茄预测（新增）

- 页面：`/tomato`；樱桃入口仍为 `/`，两者可切换。
- 页面可选择温度 0–25℃、已贮藏天数 0–23 和两种硬度指标；页面不提供比例阈值输入，计算沿用后台默认10%。API/CLI仍支持1–30%的阈值参数。
- 工作簿比例指标的实验判定口径尚未确认；**默认10%仅为演示阈值，不是经过验证的失效标准或食品安全期限**。
- 达到阈值的总时长采用同温度记录的首次跨越线性插值；非实验温度只在相邻温度的阈值时长间插值。未观测到跨越时返回无法估计，不外推。
- 剩余时间 = max(总时长 − 已贮藏天数, 0)。硬度独立展示，不用于修正该时长。
- 实测硬度组均值、时间插值、假设情景明确区分；5℃后续及10℃后续推算可信度很低。情景范围不是统计置信区间。
- 小番茄 `g/mm` 与原始整数指标不换算，不套用樱桃 `g/mm²` 或手持硬度映射。低温结果不代表无冷害。

### API 与命令行

`POST /predict` 保留原樱桃参数；省略 `product` 默认为 `cherry`。小番茄示例（需 CSRF）：

```json
{"product":"cherry_tomato","storage_temperature_c":5,"storage_days":7,"failure_threshold":0.1,"firmness_metric":"g_per_mm"}
```

此例总时长15.75天，剩余8.75天（仅针对设定阈值）。`GET /api/tomato/data` 提供来源、实测组与比例；`GET /methods` 提供方法版本。

```powershell
python predict_tomato_cli.py 5 7 --threshold-percent 10 --metric g_per_mm
python -m unittest discover -s tests -v
node --check static/tomato.js
```

命令行只依赖标准库，但需保留本项目的 `src/tomato_predictor.py` 与 `data/tomato_observations.json`。

### 数据复现

原始输入由数据所有者本地保留，未将补全值作为实测训练数据。提供原始文件目录后可重建：

```powershell
python scripts/build_tomato_data.py "原始数据所在目录"
```

详见 [数据与模型说明](data/README.md)。新增功能没有新增运行时依赖。

### 部署注意

默认监听 `127.0.0.1:5000`、关闭 debug。用环境变量 `FLASK_HOST` 和 `PORT` 配置监听地址；需要对外监听时设置 `FLASK_HOST=0.0.0.0`。保留服务器 `.env`、`instance/`、虚拟环境。更新前备份 Git 工作区差异、SQLite 和 systemd 配置，仅重启本项目服务。公开部署建议使用反向代理、HTTPS 与生产 WSGI 服务；不要把密钥或服务器密码提交到 Git。
