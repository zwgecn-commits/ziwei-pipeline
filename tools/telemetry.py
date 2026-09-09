#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telemetry.py — 可选数据回流（opt-in · 零遥测默认）

用途：
    管线作者希望了解管线在真实使用中的表现（闸门通过率/耗时/错误类型/主题分布），
    用于排盘引擎纠错与模型训练数据定向。用户报告反馈可形成 DPO 训练对。

默认行为：
    不设置 ZIWEI_TELEMETRY_URL 时**完全不发送任何数据**（本模块全部静默跳过）。
    设置后，每次管线运行结束时向该端点 POST 一条脱敏事件。

隐私设计（开发者部署收集器时须遵守）：
    1. 绝不发送原始出生信息（年月日时/性别）——只发盘面指纹的加盐哈希；
    2. 绝不发送用户身份（IP 由收集器侧脱敏/丢弃）；
    3. 反馈文本属用户自愿提交，收集器须明示用途并允许撤回。

事件 schema（v1）：
    {"v":1, "kind":"pipeline_run|gate_fail|report_feedback", "ts":"ISO8601",
     "fingerprint_hash":"sha256(salt+指纹)前16", "engine":"ziwei-chart",
     "pipeline":"0.1.0", "duration_s":12.3, "question_len":42,
     "gate_l2":"PASS", "gate_reconcile":"PASS", "error":null,
     "rating":1, "comment":"(仅反馈事件)"}
"""
import hashlib
import json
import os
import time
import urllib.request

VERSION = "0.1.0"
SALT = "ziwei-open-telemetry-v1"  # 公开盐：指纹哈希只防明文生辰泄露，不提供匿名保证

# 发送端点（部署者自备收集器；不设置则零遥测）
URL = os.environ.get("ZIWEI_TELEMETRY_URL", "")
# 可选本地事件落盘（默认关闭）
EVENT_LOG = os.environ.get("ZIWEI_EVENT_LOG", "")


def fp_hash(fingerprint: str) -> str:
    """盘面指纹加盐哈希——收集器侧无法还原出生信息。"""
    return hashlib.sha256((SALT + str(fingerprint)).encode()).hexdigest()[:16]


def emit(kind: str, **fields) -> bool:
    """发送一条事件。未配置 URL 时静默跳过；失败不抛出、不重试、不阻塞。"""
    if not URL:
        return False
    ev = {"v": 1, "kind": kind, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
          "pipeline": VERSION, **fields}
    if EVENT_LOG:
        try:
            with open(EVENT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:
            pass
    try:
        req = urllib.request.Request(
            URL, data=json.dumps(ev, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status < 300
    except Exception:
        return False


def pipeline_run(fingerprint: str, duration_s: float, question_len: int,
                 gate_l2: str = "", gate_reconcile: str = "",
                 engine: str = "ziwei-chart", error: str = "") -> bool:
    """管线运行结束事件（脱敏统计）。"""
    return emit("pipeline_run", fingerprint_hash=fp_hash(fingerprint),
                duration_s=round(duration_s, 2), question_len=question_len,
                gate_l2=gate_l2, gate_reconcile=gate_reconcile,
                engine=engine, error=error)


def report_feedback(fingerprint: str, rating: int, comment: str = "",
                    case_id: str = "") -> bool:
    """报告反馈事件（用户自愿点击 👍/👎 或提交纠错文本）。"""
    return emit("report_feedback", fingerprint_hash=fp_hash(fingerprint),
                rating=rating, comment=comment[:500], case_id=case_id)


if __name__ == "__main__":
    # 自测：未配置 URL 应零发送；配置后应返回 True
    print("URL 未配置:", "OK(零遥测)" if not URL else URL)
    r = pipeline_run("命子火六局·太禄·武权·太科·天忌", 1.2, 30, "PASS", "PASS")
    print("emit 结果:", r, "（未配置 URL 时为 False=已静默跳过）")
