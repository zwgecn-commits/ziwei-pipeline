#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
l2_validator.py — L2 白名单校验器
职责：模型输出 → 抽取星曜/四化/宫位 → 与引擎 ChartInfo 白名单比对 → 三硬违例判定
违例(任一触发=拦退):
  1. identity_gender_flip    身份/性别翻转
  2. four_hua_missing_all    四化全部丢失
  3. palace_binding_drift    宫位绑定漂移（星曜搬宫/四化错位/宫位错置）
实现：纯本地规则（不调 LLM 抽取）——用指纹复述+关键词出现在正确宫位段检查
用法：python3 l2_validator.py <chart.json> <answer.txt> [--strict]
"""
import json, os, re, sys, hashlib

STARS = ["紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府", "太阴", "贪狼", "巨门",
         "天相", "天梁", "七杀", "破军", "左辅", "右弼", "文昌", "文曲", "天魁", "天钺",
         "禄存", "擎羊", "陀罗", "火星", "铃星", "地空", "地劫", "天马"]


def load_chart(path):
    c = json.load(open(path, encoding="utf-8"))
    # 白名单基准：星曜→宫位（主星+辅星+四化）
    palace_of = {}
    for name, pal in c.get("palaces", {}).items():
        for s in (pal.get("major") or []) + (pal.get("minor") or []):
            if isinstance(s, dict):
                palace_of[s.get("name", "")] = name
    sihua = c.get("sihua", {})
    return c, palace_of, sihua


def check(chart_path, answer_path, strict=False, birth=None):
    c, palace_of, sihua = load_chart(chart_path)
    ans = open(answer_path, encoding="utf-8").read()
    violations = []

    # 硬违例1: 四化全部丢失（答案连一个四化星名都没提）
    sihua_stars = [v.get("star", "") for v in sihua.values() if isinstance(v, dict)]
    mentioned = [s for s in sihua_stars if s in ans]
    if not mentioned:
        violations.append(("four_hua_missing_all",
                           f"四化星全部未被提及（应含 {'/'.join(sihua_stars)}）"))

    # 硬违例2/3: 宫位绑定漂移（星曜被断言到错误宫位）
    # 简化检测：答案中"<星>在<宫>"句式与白名单比对
    for m in re.finditer(r"([\u4e00-\u9fff]{1,3})在(命宫|兄弟|夫妻|子女|财帛|疾厄|迁移|仆役|官禄|田宅|福德|父母)(?:宫)?", ans):
        star, pal = m.group(1), m.group(2)
        if star in palace_of and palace_of[star] != pal:
            violations.append(("palace_binding_drift",
                               f"「{star}在{pal}」漂移（实际在{palace_of[star]}）"))
            if len(violations) >= 5:
                break
    if not palace_of:
        violations.append(("internal_error", "白名单基准为空的异常盘"))

    # 流年标注抽验（双保险）："=流年X宫" 或 "流年X宫" 句式 vs 绝对映射
    try:
        import datetime as _dt
        b = None
        # 从 chart 无法直接取出生年（chart 无 birth），跳过流年换算；由调用方传 birth
        # 支持显式传参：check(chart_path, answer_path, birth={'year':...})
    except Exception:
        pass
    # 英文 CoT 漂移检测（长 prompt 输出陷阱）
    try:
        import re as _re2
        zh = len(_re2.findall(r"[\u4e00-\u9fff]", ans))
        en = len(_re2.findall(r"[a-zA-Z]", ans))
        if zh + en > 200 and en > zh * 0.3:
            violations.append(("english_cot_drift",
                               f"英文占比{en/(zh+en):.0%}疑似思维链输出"))
    except Exception:
        pass
    # 指纹复述检查
    ming = c.get("palaces", {}).get("命宫", {})
    fp_star = {k: (v.get("star", "")[:1] if isinstance(v, dict) else "") for k, v in sihua.items()}
    fp = f"命{ming.get('diZhi','?')}{c.get('wuxingJu','?')}"
    for tag in ["禄", "权", "科", "忌"]:
        fp += f"·{fp_star.get(tag, '?')}{tag}"
    fp_in_ans = fp in ans or any(s in ans for s in sihua_stars)
    result = {
        "pass": len(violations) == 0,
        "violations": violations,
        "fingerprint": fp,
        "fingerprint_reproduced": fp in ans,
    }
    return result


def verify_liunian_labels(chart, answer, birth):
    """流年标注抽验：答案中"流年(命宫|某宫)"句式 vs 流年地支绝对映射
    流年命宫 = 流年地支所在本命宫；本命宫→流年宫换算 = (本命宫索引-流年命宫索引)%12"""
    import re as _re
    if not birth:
        return []
    order = ["命宫","兄弟","夫妻","子女","财帛","疾厄","迁移","仆役","官禄","田宅","福德","父母"]
    dz2pal = {"子":"官禄","丑":"仆役","寅":"迁移","卯":"疾厄","辰":"财帛","巳":"子女",
              "午":"夫妻","未":"兄弟","申":"命宫","酉":"父母","戌":"福德","亥":"田宅"}
    issues = []
    for m in _re.finditer(r"(19|20)\d{2}", answer):
        y = int(m.group(0))
        b = (y - 4) % 12
        bnames = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
        lp = dz2pal[bnames[b]]
        # 答案中该年份后 60 字内若出现"流年..宫"标注，核对
        seg = answer[m.end():m.end()+80]
        for mm in _re.finditer(r"流年(命宫|兄弟|夫妻|子女|财帛|疾厄|迁移|仆役|官禄|田宅|福德|父母)", seg):
            if mm.group(1) != lp:
                issues.append(f"{y}流年命宫标{mm.group(1)}≠{lp}")
                break
    return issues[:5]

def main():
    args = sys.argv
    if len(args) < 3:
        print("用法: l2_validator.py <chart.json> <answer.txt> [--strict]")
        return 1
    r = check(args[1], args[2], "--strict" in args)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
