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

- 页面 `/tomato` 与樱桃 `/` 共用样式，输入 **贮藏温度＋实测硬度**，预测预计剩余货架期。不再要求输入天数，不提供比例阈值选项。
- 网页只输入 **40–90的整数硬度检测值**，不再选择指标；右侧实时显示 **FT11型映射硬度**。沿用项目既有公式 `FT11 = (检测值 - 32.714) / 0.14`，单位 g·mm⁻²；例如70 → 266.33。该式是项目既有映射，不是已验证的小番茄仪器通用标定。
- 方法：将输入检测值和小番茄原始整数组均值按同一公式转换到FT11尺度，在该曲线中反解可能的贮藏阶段，再计算 `max(参考总时长−阶段天数, 0)`。硬度真实参与计算；不是独立趋势附图，也不是已验证的逐果寿命回归模型。
- 非单调曲线可能有多个解，返回可能范围，**不随意取一个点**；范围不是置信区间。范围外不外推，5℃只有基线时返回数据不足。
- 非实测温度在相邻两温度共同时间覆盖内构建插值曲线；任何一侧缺少时间序列均不预测。
- 参考总时长来自原比例记录首次跨越默认10%的插值。**实验比例指标的判定口径尚未确认，10%是演示终点，不是已验证失效标准或食品安全期限**。页面已删除顶部长注释和“计算依据与适用限制”折叠区；计算依据保留在API结果与项目文档中。
- 不使用补全值作为新增实测；不保证低温无冷害、个体品质或实际安全。

### API 与命令行

`POST /predict` 保留原樱桃参数；省略 `product` 默认为 `cherry`。小番茄新请求（需 CSRF）：

```json
{"product":"cherry_tomato","storage_temperature_c":10,"firmness":62,"firmness_unit":"handheld"}
```

`estimated_remaining_days`（与新模式的 `estimated_shelf_life_days` 一致）表示从当前测量状态起的剩余天数；多解或不支持时为 null，需查看 `status`、`remaining_days_range` 与 `decision`。`reference_total_days` 才是从实验第0天算起的参考总时长。`candidate_stage_intervals` 保留全部支持的阶段解。

新请求不传指标时默认整数检测值自动换算；后端拒绝小数与超范围输入，不信任客户端传来的换算结果。响应包含 `handheld_hardness`、`firmness_ft11`、`firmness_g_mm2` 与 `mapping_formula`。只有显式传 `firmness_metric=g_per_mm/integer` 的旧API仍使用旧尺度，网页不提供这些选项。FT11曲线来自整数列的同公式映射，绝不将独立的 g/mm 列直接当作 g/mm²。

旧 API 显式提交 `storage_days` 时保留原天数查询行为；不可同时提交 `firmness`。省略二者报400。API/CLI阈值参数仅为旧版兼容与研究查询保留，网页不提供该选项。

```powershell
python predict_tomato_cli.py 10 --firmness 62
python -m unittest discover -s tests -v
node --check static/tomato.js
```

`GET /api/tomato/data` 提供原始来源；`GET /methods` 提供方法名称。网页FT11模式版本以 `ft11-v2` 结尾。算法只依赖标准库。

### 数据复现

原始输入由数据所有者本地保留，未将补全值作为实测训练数据。提供原始文件目录后可重建：

```powershell
python scripts/build_tomato_data.py "原始数据所在目录"
```

详见 [数据与模型说明](data/README.md)。新增功能没有新增运行时依赖。

### 部署注意

默认监听 `127.0.0.1:5000`、关闭 debug。用环境变量 `FLASK_HOST` 和 `PORT` 配置监听地址；需要对外监听时设置 `FLASK_HOST=0.0.0.0`。保留服务器 `.env`、`instance/`、虚拟环境。更新前备份 Git 工作区差异、SQLite 和 systemd 配置，仅重启本项目服务。公开部署建议使用反向代理、HTTPS 与生产 WSGI 服务；不要把密钥或服务器密码提交到 Git。
