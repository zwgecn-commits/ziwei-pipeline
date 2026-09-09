# 数据回流协议（opt-in）

> 管线作者的进化飞轮：真实使用数据 → 引擎纠错 → 模型训练定向。
> **默认零遥测**——不配置就不发送任何数据。

## 三条通道

| 通道 | 谁触发 | 发送什么 | 用途 |
|---|---|---|---|
| ① 运行遥测 | 管线部署者（`ZIWEI_TELEMETRY_URL` 配置后） | 指纹加盐哈希/耗时/闸门结果/错误类型 | 定位薄弱环节、观测闸门通过率 |
| ② 报告反馈 | 最终用户点 👍/👎（部署者配置 `ZIWEI_FEEDBACK_URL` 后渲染按钮） | rating + 盘面指纹 + 案例号 | 负反馈 → DPO 训练对 |
| ③ 对账众包 | 最终用户（ziwei-chart 引擎 README 的网页通道） | 文墨天机对账差异 | 引擎 bug 修复 → 一切下游数据变准 |

## 部署（管线作者侧）

```bash
# 运行遥测：POST 脱敏事件到你的收集器
export ZIWEI_TELEMETRY_URL=https://your-server/api/telemetry
# 可选本地事件留档
export ZIWEI_EVENT_LOG=./events.jsonl

# 报告反馈按钮：渲染 HTML 前设置，用户点 👍👎 回传
export ZIWEI_FEEDBACK_URL=https://your-server/api/report-feedback
```

`tools/telemetry.py` 提供 `pipeline_run()` / `report_feedback()` 两个入口，
可在自己部署的服务端代码里直接调用。

## 隐私红线（收集器部署者必须遵守）

1. **绝不收集原始出生信息**——telemetry 只发指纹哈希；若你在服务端留存
   生辰（如对账众包），须单独告知用户、单独同意、可撤回、可删除。
2. **反馈文本**属用户自愿内容，明示用途，提供撤回途径。
3. **服务端去身份化**：不关联账号/手机号/IP 到单条事件；聚合统计优先。
4. 遵守所在地法律法规（中国 PIPL / 欧盟 GDPR 等）。生辰属敏感个人信息。

## 收集器参考实现（最小示例）

```python
# collector.py — Flask 最小收集器
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.post("/api/telemetry")
def telemetry():
    ev = request.get_json(force=True)
    with open("telemetry.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return jsonify({"ok": True})

@app.post("/api/report-feedback")
def feedback():
    ev = request.get_json(force=True)   # {rating, case_id, fingerprint}
    with open("feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return jsonify({"ok": True})
```

反馈事件按 rating 分桶后：`rating=-1` 的盘面 → 回看该案例产物 → 修正后进 DPO 对；
`rating=1` 的案例 → 优质正样本。遥测的 `gate_l2`/`error` 字段分布 → 优先修高频失败形态。

## 如何让数据"对模型有利"（闭环步骤）

1. 反馈负样本 → 人审/教师模型纠正 → `(坏输出, 好输出)` DPO 对
2. 遥测薄弱环节（如某类问题 L2 违例率高）→ 用 `gen_daxian_map_qa.py` 同法
   程序化定向出题 → 并入训练集
3. 对账差异 → 修引擎 → 重跑训练数据工厂 → 全盘数据质量提升
4. 训练配方见 [training-recipe.md](training-recipe.md)
