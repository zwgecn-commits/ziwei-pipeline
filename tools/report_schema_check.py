#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_schema_check.py — 六件套呈现契约校验器 v2
================================================================
职责：校验紫微阁交付报告 JSON 是否符合 report/v1 六件套契约。
v2 变更：纯标准库自写校验（无 jsonschema 依赖），免安装即用。
用法：python3 report_schema_check.py [report.json] | --render-example
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.environ.get("REPORT_EXAMPLE", os.path.join(_HERE, "report_example.json"))

# __name__ 要求顶层六件套字段
_REQUIRED_TOP = ["schema_version", "meta", "chart_facts", "rule_verdict", "sections", "scores", "gate"]

_META = ["case_id", "gender", "deidentified", "fingerprint", "engine", "wuxing_ju", "laiyin", "timestamp"]
_FACTS = ["ming", "shen", "palaces", "sihua_birth", "daxian", "liunian"]
_RULE = ["p0", "p1", "fingerprint_verify"]
_SECTION = ["id", "title", "verdict", "technique_trace"]
_SCORES = ["liugong_lu", "formula", "rules_engine_signal", "verdict"]
_GATE = ["l2_lower", "reconcile", "hard_error_rate", "upper_gate"]

_OK = {"l2_lower": {"PASS", "FAIL", "DEGRADED"}, "reconcile": {"PASS", "FAIL"}}


def _check_fields(obj: dict, required: list, path: str) -> list:
    errs = []
    for k in required:
        if k not in obj:
            errs.append(f"{path}: 缺字段 '{k}'")
    return errs


def validate(report: dict) -> list:
    """纯标准库校验·返回错误列表（空=通过）"""
    errs = []
    # 顶层
    errs += _check_fields(report, _REQUIRED_TOP, "<root>")
    if report.get("schema_version") != "report/v1":
        errs.append(f"<root>.schema_version 应为 'report/v1'，实为 {report.get('schema_version')!r}")
    m = report.get("meta", {})
    errs += _check_fields(m, _META, "meta")
    if m.get("gender") not in ("男", "女"):
        errs.append(f"meta.gender 应为 男/女，实为 {m.get('gender')!r}")
    if not isinstance(m.get("fingerprint", ""), str) or "局" not in m.get("fingerprint", ""):
        errs.append("meta.fingerprint 格式异常（应含'命X局…'指纹串）")
    f = report.get("chart_facts", {})
    errs += _check_fields(f, _FACTS, "chart_facts")
    if not isinstance(f.get("palaces", []), list) or len(f.get("palaces", [])) != 12:
        errs.append("chart_facts.palaces 应为 12 宫")
    if not isinstance(f.get("daxian", []), list) or len(f.get("daxian", [])) != 12:
        errs.append("chart_facts.daxian 应为 12 限")
    sw = f.get("sihua_birth", {})
    for k in ("禄", "权", "科", "忌"):
        if k not in sw:
            errs.append(f"chart_facts.sihua_birth 缺 '{k}'")
    r = report.get("rule_verdict", {})
    errs += _check_fields(r, _RULE, "rule_verdict")
    for k, total in (("p0", 18), ("p1", 14)):
        sub = r.get(k, {})
        if not isinstance(sub, dict) or sub.get("total") != total:
            errs.append(f"rule_verdict.{k}.total 应为 {total}")
        elif sub.get("hit", 0) > total:
            errs.append(f"rule_verdict.{k}.hit 超上限")
    secs = report.get("sections", [])
    if not isinstance(secs, list) or len(secs) < 1:
        errs.append("sections 应至少 1 节")
    for i, s in enumerate(secs):
        errs += _check_fields(s, _SECTION, f"sections[{i}]")
    sc = report.get("scores", {})
    errs += _check_fields(sc, _SCORES, "scores")
    if not isinstance(sc.get("liugong_lu", {}), dict):
        errs.append("scores.liugong_lu 应为对象")
    g = report.get("gate", {})
    errs += _check_fields(g, _GATE, "gate")
    for k, allowed in _OK.items():
        if k in g and g.get(k) not in allowed:
            errs.append(f"gate.{k} 应为 {'/'.join(allowed)}，实为 {g.get(k)!r}")
    if not isinstance(g.get("hard_error_rate", 0), (int, float)) or not (0 <= g.get("hard_error_rate", -1) <= 1):
        errs.append("gate.hard_error_rate 应在 [0,1]")
    if g.get("upper_gate") is not True:
        errs.append("gate.upper_gate 应为 true（可上线交付）")
    return errs


def _demo(show: bool = True):
    """自检：正例 PASS + 负例 FAIL"""
    ok_errs = validate(json.load(open(EXAMPLE, encoding="utf-8")))
    print(f"正例({EXAMPLE}): {'PASS' if not ok_errs else ok_errs[:3]}")
    bad = json.load(open(EXAMPLE, encoding="utf-8"))
    del bad["gate"]["l2_lower"]
    bad_errs = validate(bad)
    print(f"负例(删 l2_lower): {'FAIL-正确' if bad_errs else 'ERROR-漏检'} {bad_errs[:2]}")
    return not ok_errs and bool(bad_errs)


if __name__ == "__main__":
    if "--render-example" in sys.argv:
        sys.exit(0 if _demo() else 1)
    path = sys.argv[1] if len(sys.argv) > 1 else EXAMPLE
    try:
        report = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(f"❌ 读取失败: {e}"); sys.exit(1)
    errs = validate(report)
    print(f"契约校验: {path}")
    if not errs:
        print("✅ PASS: 六件套契约全部满足（可进模板渲染）"); sys.exit(0)
    for e in errs:
        print(f"❌ {e}")
    sys.exit(1)
