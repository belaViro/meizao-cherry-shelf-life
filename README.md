# 樱桃货架期预测系统

这是一个基于 Flask、LangChain 和 SQLite 的樱桃货架期预测 Web 应用。系统支持用户账号、自动保存预测历史、数据可视化，以及将个人历史记录导出为 Excel。

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

其中 `T` 是贮藏温度（℃），`L` 是基础货架期（天）。系统保留原始多项式和硬度修正逻辑，并使用温度—硬度二维对数空间高斯径向基校准，使“0 ℃、手持硬度 70 = 37 天”“5 ℃、手持硬度 70 = 25 天”和“25 ℃、手持硬度 60 = 2 天”三个参考点精确命中。校准面在温度和硬度方向均连续，离开参考点后会平滑回归原始模型，避免使用条件判断写死结果。

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

## 启动

```powershell
python app.py
```

浏览器访问：

```text
http://127.0.0.1:5000
```

首次使用时先注册账号。SQLite 数据库会自动创建在：

```text
instance/meizao.sqlite3
```

## 页面功能

1. 注册或登录个人账号。
2. 选择 0、5、10、15、20 或 25 ℃。
3. 输入 50-90 范围的手持式硬度计读数。
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

浏览器页面的 POST 请求带有 CSRF 校验。如果使用脚本直接调用 `/predict`，需要先登录并携带会话 Cookie 和 `X-CSRF-Token` 请求头。

## 数据说明

- 每个用户只能查看和导出自己的预测历史。
- 密码只保存哈希值，不保存明文。
- 历史数据保存在本地 SQLite 数据库中。
- 部署到 HTTPS 环境时，建议将 Flask 的 `SESSION_COOKIE_SECURE` 配置为 `True`。
