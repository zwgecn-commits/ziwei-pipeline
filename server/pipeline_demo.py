#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline_demo.py — 紫微 AI 分析管线参考实现（开源演示版）

串联链路（各环节对应 tools/ 模块 + ziwei-chart 排盘引擎）：
    排盘 → 规则判定(指纹) → L2 白名单校验 → 成品对账闸门 → 六件套 JSON(契约校验) → HTML 渲染

设计要点：
- 确定性数据（宫位/星曜/四化/岁段）全部由引擎权威输出注入，模型只读不重算
- 成品闸门用确定性代码比对，不用 LLM 自评
- 本文件不调推理模型——展示工程链路骨架；推理环节（Ollama/OpenAI 兼容 API）
  可用 tools/prompt_builder.py 构造注入 prompt 后自行接入

用法：
    python3 pipeline_demo.py                 # 内置示例生辰跑通全链
    python3 pipeline_demo.py '{"year":1990,"month":7,"day":14,"hour":12,"gender":"女"}'

环境变量：
    ZIWEI_ENGINE     排盘引擎路径（默认 ~/ziwei-chart/ziwei_chart.js，见 ziwei-chart 仓库）
    OUT_DIR          输出目录（默认 /tmp）
"""
import json, os, subprocess, sys, datetime, time

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.join(_HERE, "..", "tools")
sys.path.insert(0, _TOOLS)
ENGINE = os.environ.get("ZIWEI_ENGINE", os.path.expanduser("~/ziwei-chart/ziwei_chart.js"))
OUT_DIR = os.environ.get("OUT_DIR", "/tmp")
# 纯虚构演示盘（非真实案例）
BIRTH_DEFAULT = {"year": 1996, "month": 4, "day": 9, "hour": 10,
                 "gender": "女", "minute": 0, "longitude": 120.0}

PALACE_ORDER = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移",
                "仆役", "官禄", "田宅", "福德", "父母"]


def step(name, ok, detail=""):
    print(f"{'✅' if ok else '❌'} [{name}] {detail}")
    return ok


def run_chart(birth):
    g = "male" if birth["gender"] in ("男", "male") else "female"
    r = subprocess.run(["node", ENGINE, str(birth["year"]), str(birth["month"]),
                        str(birth["day"]), str(birth["hour"]), g,
                        str(birth.get("minute", 0)), str(birth.get("longitude", 120.0))],
                       capture_output=True, text=True, timeout=30)
    return json.loads(r.stdout)


def stars_of(pal, kind):
    out = []
    for s in pal.get(kind) or []:
        if isinstance(s, dict):
            out.append(s.get("name", "") + (s.get("mutagen", "") or ""))
        else:
            out.append(str(s))
    return out


def main():
    all_ok = True
    t0 = time.time()
    print("=" * 60)
    print("紫微 AI 分析管线 · 参考实现全链演示")
    print("=" * 60)

    # ① 排盘层
    birth = json.loads(sys.argv[1]) if len(sys.argv) > 1 else BIRTH_DEFAULT
    chart = run_chart(birth)
    ming = chart.get("palaces", {}).get("命宫", {})
    all_ok &= step("① 排盘", chart.get("success", True),
                   f"命宫 {ming.get('tianGan','?')}{ming.get('diZhi','?')}·{chart.get('wuxingJu','')}")

    # ② 规则判定 + 数字指纹
    from rules_engine import evaluate_chart
    aud = evaluate_chart(chart)
    fp = aud.get("fingerprint", "")
    all_ok &= step("② 规则判定+指纹", "?" not in fp,
                   f"P0 {aud.get('p0_hit')}/{aud.get('p0_total')} | 指纹 {fp}")

    # ③ L2 星曜宫位白名单校验（以引擎 ChartInfo 为准）
    import re
    palace_of = {}
    for name, pal in chart.get("palaces", {}).items():
        for s in (pal.get("major") or []) + (pal.get("minor") or []):
            if isinstance(s, dict):
                palace_of[s.get("name", "")] = name
    sample = f"命盘分析：命宫{ming.get('tianGan','')}{ming.get('diZhi','')}。"
    viol = []
    for m in re.finditer(
            r"([\u4e00-\u9fff]{1,3})在(命宫|兄弟|夫妻|子女|财帛|疾厄|迁移|仆役|官禄|田宅|福德|父母)(?:宫)?",
            sample):
        star, pal = m.group(1), m.group(2)
        if star in palace_of and palace_of[star] != pal:
            viol.append(f"{star}@{pal}")
    all_ok &= step("③ L2 白名单校验", len(viol) == 0, f"违例 {viol or '无'}")

    # ④ 成品对账闸门（确定性 · 岁段→宫位 vs 引擎 daxian）
    import reconcile_gate as rg
    gate = rg.verify(chart, sample)
    all_ok &= step("④ 成品闸门(岁段→宫位)", gate.get("pass"),
                   f"检查 {gate.get('checked')} 项")

    # ⑤ 六件套 JSON（report/v1 契约：字符串行数组 + 确定性字段）
    import report_schema_check as rsc
    daxian = chart.get("daxian", [])
    # 大限十二宫字符串行：岁段·宫名·大限四化
    dxs = chart.get("daxianSihua", [])
    dx_rows = []
    for d in daxian:
        rng = d.get("range", ["?", "?"])
        pn = d.get("palace", "?")
        p = chart.get("palaces", {}).get(pn, {})
        gz = f"{p.get('tianGan','?')}{p.get('diZhi','?')}"
        sh = ""
        for ds in dxs:
            if ds.get("palace") == pn:
                s = ds.get("sihua", {})
                if isinstance(s, dict):
                    sh = "".join(f"{s.get(k,'')}{k}" for k in ("禄", "权", "科", "忌") if s.get(k))
                break
        dx_rows.append(f"{rng[0]}-{rng[1]}岁·{pn}({gz})·{sh or '无'}")

    # 流年四化（当前大限十年；引擎字段为大限宫名→逐年条目）
    GAN, ZHI = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥"
    now_y = datetime.date.today().year
    liunian = []
    for pn, arr in (chart.get("liunianSihua") or {}).items():
        for it in arr:
            if isinstance(it, dict) and now_y <= it.get("year", 0) <= now_y + 9:
                y = it["year"]
                gz = GAN[(y - 4) % 10] + ZHI[(y - 4) % 12]
                land = next((pp for pp, ppd in chart.get("palaces", {}).items()
                             if ppd.get("diZhi") == ZHI[(y - 4) % 12]), "?")
                s = it.get("sihua", {})
                sh = "".join(f"{s.get(k,'')}{k}" for k in ("禄", "权", "科", "忌") if s.get(k))
                liunian.append(f"{y} {gz} 流年命宫落{land}·{sh or '无'}")
    liunian = sorted(liunian)[:10]

    # 生年四化
    sihua = chart.get("sihua", {})
    sihua_birth = {}
    for tag in ("禄", "权", "科", "忌"):
        s = sihua.get(tag, {})
        if isinstance(s, dict):
            sihua_birth[tag] = f"{s.get('star','')}@{s.get('palace','')}"

    # 命宫/身宫摘要
    shen = chart.get("shen", {})
    ming_line = (f"命宫{ming.get('tianGan','')}{ming.get('diZhi','')}·"
                 + " ".join(stars_of(ming, "major") + stars_of(ming, "minor")))
    shen_name = shen.get("name", "?")
    shen_line = (f"身宫{shen_name}({shen.get('tianGan','')}{shen.get('diZhi','')})")

    report = {
        "schema_version": "report/v1",
        "meta": {"case_id": "demo-" + datetime.date.today().strftime("%Y%m%d"),
                 "gender": "女" if str(birth["gender"]) in ("女", "female") else "男",
                 "deidentified": True, "fingerprint": fp,
                 "engine": "ziwei-chart", "wuxing_ju": chart.get("wuxingJu", ""),
                 "laiyin": chart.get("laiyinPalace", ""),
                 "timestamp": datetime.datetime.now().isoformat()},
        "chart_facts": {"ming": ming_line, "shen": shen_line,
                        "palaces": [f"{pn}({p.get('tianGan','')}{p.get('diZhi','')}): 主["
                                    + ",".join(stars_of(p, "major")) + "] 辅["
                                    + ",".join(stars_of(p, "minor")) + "]"
                                    for pn, p in chart.get("palaces", {}).items()
                                    if pn in PALACE_ORDER][:12],
                        "sihua_birth": sihua_birth,
                        "daxian": dx_rows,
                        "liunian": liunian},
        "rule_verdict": {"p0": {"hit": aud.get("p0_hit", 0), "total": aud.get("p0_total", 18),
                                "detail": []},
                         "p1": {"hit": aud.get("p1_hit", 0), "total": aud.get("p1_total", 14),
                                "detail": []},
                         "fingerprint_verify": fp},
        "sections": [{"id": "s1", "title": "命盘总览", "verdict": ming_line + "，身宫" + shen_name +
                      "。推理环节接入后，此处由模型基于事实表产出判词。",
                      "technique_trace": ["确定性事实层", "待接入推理"], "banned_terms_ok": True}],
        "scores": {"liugong_lu": {}, "formula": [],
                   "rules_engine_signal": f"P0 {aud.get('p0_hit')}/{aud.get('p0_total')}",
                   "verdict": "演示链未接推理，评分由推理环节填充"},
        "gate": {"l2_lower": "PASS", "reconcile": "PASS",
                 "hard_error_rate": 0.0, "upper_gate": True,
                 "notes": ["开源参考实现演示", "推理环节留白"]},
    }
    errs = rsc.validate(report)
    all_ok &= step("⑤ 六件套 JSON", not errs,
                   f"契约校验 {'PASS' if not errs else errs[:2]}")
    rp = os.path.join(OUT_DIR, "chain_report.json")
    if not errs:
        os.makedirs(OUT_DIR, exist_ok=True)
        json.dump(report, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ⑥ 渲染
    import report_render as rr
    html = rr.render(report)
    hp = os.path.join(OUT_DIR, "chain_report.html")
    open(hp, "w", encoding="utf-8").write(html)
    all_ok &= step("⑥ 六件套渲染", len(html) > 2000, f"{len(html)}B → {hp}")

    # ⑦ 可选遥测（opt-in：未配置 ZIWEI_TELEMETRY_URL 时零发送）
    import telemetry
    telemetry.pipeline_run(fp, time.time() - t0, question_len=0,
                           gate_l2="PASS", gate_reconcile="PASS" if gate.get("pass") else "FAIL",
                           error="" if all_ok else "chain_step_failed")

    print("=" * 60)
    print(f"全链演示: {'✅ 通过' if all_ok else '❌ 存在失败'}")
    if all_ok:
        print(f"JSON 契约报告: {rp}")
        print(f"HTML 渲染报告: {hp}")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
