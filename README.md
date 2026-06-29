# 美早樱桃货架期预测 Flask 项目

这是一个 Flask + LangChain 项目。接口接收贮藏温度和硬度，支持两种货架期判断方法，并统一返回结构化 JSON。

## 两种预测方法

1. `polynomial_regression`

使用三次多项式回归直接计算温度对应的基础货架期：

```text
L = -0.00125926*T^3 + 0.0536508*T^2 - 1.03201*T + 17.00794
```

其中 `T` 是贮藏温度，单位为摄氏度；`L` 是基础货架期，单位为天。接口会再根据输入硬度做修正。

2. `llm_structured`

通过 LangChain 调用硅基流动的 OpenAI-compatible API，默认模型为 `Qwen/Qwen2.5-7B-Instruct`。模型输出会被提取为 JSON，并用 Pydantic 的 `ShelfLifePrediction` 结构校验后返回。

## 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 配置硅基流动

本地 `.env` 示例：

```text
SILICONFLOW_API_KEY=你的硅基流动 Key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=Qwen/Qwen2.5-7B-Instruct
```

`.env` 已在 `.gitignore` 中排除，不会提交。

## 启动

```bash
python app.py
```

默认地址：

```text
http://127.0.0.1:5000
```

## 接口

### 查看方法

```bash
curl http://127.0.0.1:5000/methods
```

### 多项式回归预测

```bash
curl -X POST http://127.0.0.1:5000/predict ^
  -H "Content-Type: application/json" ^
  -d "{\"storage_temperature_c\": 2, \"firmness\": 70, \"firmness_unit\": \"handheld\", \"prediction_method\": \"polynomial_regression\"}"
```

### LLM 结构化输出预测

```bash
curl -X POST http://127.0.0.1:5000/predict ^
  -H "Content-Type: application/json" ^
  -d "{\"storage_temperature_c\": 2, \"firmness\": 70, \"firmness_unit\": \"handheld\", \"prediction_method\": \"llm_structured\"}"
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `storage_temperature_c` | number | 是 | 贮藏温度，固定选项为 0、5、10、15、20、25 摄氏度 |
| `firmness` | number | 是 | 手持式硬度计读数，必须在 50-90 之间；按 50->200、70->380、90->500 分段线性映射到 g·mm⁻² |
| `firmness_unit` | string | 否 | 硬度单位固定为 `handheld`，页面自动提交 |
| `prediction_method` | string | 否 | `polynomial_regression` 或 `llm_structured`，默认 `polynomial_regression` |







