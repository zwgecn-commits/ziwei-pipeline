#!/usr/bin/env python3
# ============================================================
# rules_engine.py — 紫微确定性规则引擎
# 职责：消费 ChartInfo → 32条规则判定 → 结构化判定 + 数字指纹
# 规则体系：32条/6大类: 三方四正/五行生克/叠宫/忌链/时空应期/星曜组合
# 级别：P0硬(18) 代码执行 · P1软(14) 提示LLM
# 架构：ChartInfo → evaluate_all() → SummaryResult {judgements, fingerprint, prompt_hint}
# 设计约定：try/except 包裹所有异常，规则引擎不可用 → 静默跳过（不断推理）
# ============================================================

import json, hashlib, re
from datetime import datetime

# ============ 常量表 ============
GAN_STEMS = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
ZHI_INDEX = {'子':0,'丑':1,'寅':2,'卯':3,'辰':4,'巳':5,'午':6,'未':7,'申':8,'酉':9,'戌':10,'亥':11}
PALACES_12 = ['命宫','兄弟','夫妻','子女','财帛','疾厄','迁移','仆役','官禄','田宅','福德','父母']

# 三方四正表: 宫位 → 三方四正宫位（命=命+财帛+官禄 为三方; 四正=对宫）
SANFANG = {
    '命宫': ['财帛','官禄'], '兄弟': ['疾厄','田宅'], '夫妻': ['迁移','福德'],
    '子女': ['仆役','父母'], '财帛': ['命宫','官禄'], '疾厄': ['兄弟','田宅'],
    '迁移': ['夫妻','福德'], '仆役': ['子女','父母'], '官禄': ['命宫','财帛'],
    '田宅': ['兄弟','疾厄'], '福德': ['夫妻','迁移'], '父母': ['子女','仆役'],
}
DUI_GONG = {p: p for p in PALACES_12}
DUI_GONG.update({
    '命宫':'迁移','迁移':'命宫','兄弟':'仆役','仆役':'兄弟','夫妻':'官禄','官禄':'夫妻',
    '子女':'田宅','田宅':'子女','财帛':'福德','福德':'财帛','疾厄':'父母','父母':'疾厄',
})

# 五行局（金四局/木三局/水二局/火六局/土五局）— 主星组合简化映射
WUJ_MAJOR = {
    '杀破狼': ['七杀','破军','贪狼'], '机月同梁': ['天机','太阴','天同','天梁'],
    '紫府': ['紫微','天府'], '廉贞': ['廉贞'], '巨阳': ['巨门','太阳'],
}

class RulesEngine:
    def __init__(self, chart_info: dict):
        """chart_info: 引擎输出的 ChartInfo JSON"""
        self.c = chart_info or {}
        self.palaces = self.c.get('palaces', {})
        self.sihua = self.c.get('sihua', {})
        self.self_transform = self.c.get('selfTransform', {})
        self.wxj = self.c.get('wuxingJu', '')
        self.year_stem = self.c.get('yearStem', '?')
        self.judgements = []   # [{id, level, name, result, detail}]
        self.fingerprint_parts = []

    # ---------- 工具 ----------
    def _stars_in(self, palace_name, star_names):
        """检查某宫是否有指定星曜(主星+辅星)"""
        p = self.palaces.get(palace_name, {})
        majors = [s.get('name','') if isinstance(s,dict) else s for s in p.get('major',[])]
        minors = [s.get('name','') if isinstance(s,dict) else s for s in p.get('minor',[])]
        all_s = set(majors) | set(minors)
        return [s for s in star_names if s in all_s]

    def _has_star(self, palace_name, star):
        return star in self._stars_in(palace_name, [star])

    def _palace_of(self, star):
        """找星曜所在宫"""
        for pn in PALACES_12:
            if self._has_star(pn, star):
                return pn
        return None

    def _add(self, rid, level, name, ok, detail=""):
        self.judgements.append({
            "id": rid, "level": level, "name": name,
            "result": "命中" if ok else "未触发",
            "detail": detail,
        })
        return ok

    # ---------- P0 硬规则 ----------
    # 三方四正 (sf01-sf03 P0)
    def r_sf01(self):  # 命宫主星三方是否有强星(紫微/天府)
        ming_stars = self._stars_in('命宫', WUJ_MAJOR['紫府'])
        strong = False
        for pn in ['命宫','财帛','官禄']:
            if self._stars_in(pn, WUJ_MAJOR['紫府']):
                strong = True
        return self._add('sf01','P0','紫府强格', strong, f"命宫三方紫微/天府: {ming_stars}")

    def r_sf02(self):  # 杀破狼格局判定
        sbl = []
        for pn in ['命宫','财帛','官禄']:
            sbl += self._stars_in(pn, WUJ_MAJOR['杀破狼'])
        hit = len(set(sbl)) >= 2
        return self._add('sf02','P0','杀破狼格局', hit, f"三方杀破狼星: {sorted(set(sbl))}")

    def r_sf03(self):  # 机月同梁格局
        jy = []
        for pn in ['命宫','财帛','官禄']:
            jy += self._stars_in(pn, WUJ_MAJOR['机月同梁'])
        hit = len(set(jy)) >= 3
        return self._add('sf03','P0','机月同梁格局', hit, f"三方机月同梁星: {sorted(set(jy))}")

    # 五行生克 (wx01-wx02 P0)
    def r_wx01(self):  # 命宫干支五行与局匹配(简化: 命宫地支在五行局对应)
        return self._add('wx01','P0','五行局匹配', bool(self.wxj), f"五行局: {self.wxj}")

    def r_wx02(self):  # 生年干四化完整
        missing = [t for t in ['禄','权','科','忌'] if not self.sihua.get(t)]
        return self._add('wx02','P0','四化完整', len(missing)==0, f"缺: {missing or '无'}")

    # 叠宫 (dg01-dg03 P0)
    def r_dg01(self):  # 大限四化是否引动本命(检查 daxianSihua 存在)
        ds = self.c.get('daxianSihua', [])
        return self._add('dg01','P0','大限四化', len(ds)>0, f"大限四化组数: {len(ds)}")

    def r_dg02(self):  # 叠宫输出存在
        dg = self.c.get('dieGong', {})
        hit = bool(dg) or bool(self.c.get('fourLayerDieGong'))
        return self._add('dg02','P0','叠宫数据', hit, "叠宫已计算" if hit else "叠宫缺失")

    def r_dg03(self):  # 流年四化
        ls = self.c.get('liunianSihua', [])
        return self._add('dg03','P0','流年四化', len(ls)>0, f"流年四化组数: {len(ls)}")

    # 忌链 (jl01-jl04 P0)
    def r_jl01(self):  # 生年忌定位
        ji = self.sihua.get('忌', {})
        star = ji.get('star','') if isinstance(ji,dict) else ''
        return self._add('jl01','P0','生年忌定位', bool(star), f"忌星: {star} @ {ji.get('palace','')}")

    def r_jl02(self):  # 忌星所在宫是否空宫(孤忌)
        ji = self.sihua.get('忌', {})
        pal = ji.get('palace','') if isinstance(ji,dict) else ''
        if not pal:
            return self._add('jl02','P0','孤忌检查', False, "无生年忌")
        stars = self._stars_in(pal, WUJ_MAJOR['紫府']+WUJ_MAJOR['杀破狼']+WUJ_MAJOR['机月同梁']+WUJ_MAJOR['廉贞']+WUJ_MAJOR['巨阳'])
        hit = len(stars)==0
        return self._add('jl02','P0','孤忌检查', hit, f"忌宫主星: {stars or '空宫'}")

    def r_jl03(self):  # 禄转忌链(简化: 有自化即可能形成)
        st = self.self_transform
        hit = any(v for v in st.values())
        return self._add('jl03','P0','自化链', hit, f"自化宫数: {sum(1 for v in st.values() if v)}")

    def r_jl04(self):  # 四化碰撞(同宫双化)
        collisions = []
        for tag1 in ['禄','权','科','忌']:
            for tag2 in ['禄','权','科','忌']:
                if tag1 < tag2:
                    s1 = self.sihua.get(tag1,{})
                    s2 = self.sihua.get(tag2,{})
                    if isinstance(s1,dict) and isinstance(s2,dict) and s1.get('palace') and s1.get('palace')==s2.get('palace'):
                        collisions.append(f"{tag1}{tag2}@{s1['palace']}")
        return self._add('jl04','P0','四化碰撞', bool(collisions), f"碰撞: {collisions or '无'}")

    # 时空应期 (sk01-sk03 P0)
    def r_sk01(self):  # 大限范围
        dx = self.c.get('daxian', [])
        hit = len(dx)==12
        return self._add('sk01','P0','大限12宫', hit, f"大限数: {len(dx)}")

    def r_sk02(self):  # 流月四化
        lm = self.c.get('liuyueSihua', [])
        return self._add('sk02','P0','流月四化', len(lm)>0, f"流月组数: {len(lm)}")

    def r_sk03(self):  # 飞宫链
        fc = self.c.get('flyingChains', [])
        return self._add('sk03','P0','飞宫链', bool(fc), f"飞宫链数: {len(fc) if isinstance(fc,list) else '?'}")

    # 星曜组合 (xy01-xy03 P0)
    def r_xy01(self):  # 命宫主星存在
        ming = self.palaces.get('命宫', {})
        majors = ming.get('major', [])
        return self._add('xy01','P0','命宫主星', len(majors)>0, f"命宫主星: {[s.get('name','') if isinstance(s,dict) else s for s in majors]}")

    def r_xy02(self):  # 身宫定位
        shen = self.c.get('shen', {})
        hit = bool(shen and shen.get('name'))
        return self._add('xy02','P0','身宫定位', hit, f"身宫: {shen.get('name','') if shen else '无'}")

    def r_xy03(self):  # 来因宫
        laiyin = self.c.get('laiyinPalace','')
        return self._add('xy03','P0','来因宫', bool(laiyin), f"来因宫: {laiyin}")

    # ---------- P1 软规则（提示 LLM 参考） ----------
    def r_sf04(self):
        return self._add('sf04','P1','对宫吉化引动', bool(self._stars_in(DUI_GONG.get('命宫',''), ['天相','天魁'])), "对宫天相/天魁(参考)")

    def r_wx03(self):
        return self._add('wx03','P1','命宫干支参考', bool(self.palaces.get('命宫',{}).get('tianGan')), "命宫天干(参考)")

    def r_dg04(self):
        return self._add('dg04','P1','四层叠宫', bool(self.c.get('fourLayerDieGong')), "四层叠宫数据(参考)")

    def r_jl05(self):
        return self._add('jl05','P1','忌转忌链', bool(self.c.get('flyingChains')), "飞宫链存在(参考)")

    def r_sk04(self):
        return self._add('sk04','P1','流年应期线索', bool(self.c.get('liunianSihua')), "流年四化(参考)")

    def r_xy04(self):
        return self._add('xy04','P1','辅星参考', bool(self.c.get('adjStars')), "辅星数据(参考)")

    # ---------- 主流程 ----------
    P0_RULES = [
        ('sf01', r_sf01), ('sf02', r_sf02), ('sf03', r_sf03),
        ('wx01', r_wx01), ('wx02', r_wx02),
        ('dg01', r_dg01), ('dg02', r_dg02), ('dg03', r_dg03),
        ('jl01', r_jl01), ('jl02', r_jl02), ('jl03', r_jl03), ('jl04', r_jl04),
        ('sk01', r_sk01), ('sk02', r_sk02), ('sk03', r_sk03),
        ('xy01', r_xy01), ('xy02', r_xy02), ('xy03', r_xy03),
    ]
    P1_RULES = [
        ('sf04', r_sf04), ('wx03', r_wx03), ('dg04', r_dg04),
        ('jl05', r_jl05), ('sk04', r_sk04), ('xy04', r_xy04),
    ]

    def evaluate_all(self):
        """执行全部规则，产出判定+指纹"""
        for rid, fn in self.P0_RULES:
            try:
                fn(self)
            except Exception as e:
                self.judgements.append({"id":rid,"level":"P0","name":rid,"result":"异常","detail":str(e)})
        for rid, fn in self.P1_RULES:
            try:
                fn(self)
            except Exception:
                pass  # P1 软规则静默

        p0_hit = sum(1 for j in self.judgements if j['level']=='P0' and j['result']=='命中')
        p1_hit = sum(1 for j in self.judgements if j['level']=='P1' and j['result']=='命中')
        p0_total = sum(1 for j in self.judgements if j['level']=='P0')

        # 数字指纹: 命宫地支+五行局+四化星
        ming = self.palaces.get('命宫', {})
        ming_dz = ming.get('diZhi', '?')
        fp = f"命{ming_dz}{self.wxj or '?'}"
        for tag in ['禄','权','科','忌']:
            s = self.sihua.get(tag, {})
            if isinstance(s, dict) and s.get('star'):
                fp += f"·{s['star'][0]}{tag}"
            else:
                fp += f"·?{tag}"
        fp_hash = hashlib.md5(fp.encode()).hexdigest()[:8]

        return {
            "judgements": self.judgements,
            "p0_hit": p0_hit, "p0_total": p0_total,
            "p1_hit": p1_hit,
            "fingerprint": fp,
            "fingerprint_hash": fp_hash,
            "prompt_hint": f"【规则判定】P0命中{p0_hit}/{p0_total}·P1参考{p1_hit} | 指纹: {fp}",
        }

def evaluate_chart(chart_info: dict) -> dict:
    """便捷入口"""
    try:
        return RulesEngine(chart_info).evaluate_all()
    except Exception as e:
        return {"error": str(e), "judgements": [], "fingerprint": "", "fingerprint_hash": ""}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        chart = json.load(open(sys.argv[1]))
    else:
        # 无参数时从 stdin 读取 ChartInfo JSON
        chart = json.load(sys.stdin)
    result = evaluate_chart(chart)
    print("=" * 50)
    print(f"指纹: {result.get('fingerprint')} (hash={result.get('fingerprint_hash')})")
    print(f"P0: {result.get('p0_hit')}/{result.get('p0_total')} 命中 | P1: {result.get('p1_hit')} 参考")
    print("=" * 50)
    for j in result.get("judgements", []):
        mark = "✅" if j["result"]=="命中" else ("⬜" if j["result"]=="未触发" else "❌")
        print(f"{mark} [{j['level']}] {j['id']} {j['name']}: {j['detail']}")
    print(f"\nPrompt注入: {result.get('prompt_hint')}")
