#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
好好说话 · 评测尺 v3(三维合成一个统一分,保真 > 通顺 > AI味)

每日召回(loop.py)只用这里的残留正则和 new_number_prescreen 给机械检查抬旗,
命中只当提示,由裁判逐条确认。统一分不参与任何发布判断:原样不改的"改写"
在 50 条上平均 94.5 分,比三个真工具都高,它量不出失真。

—— 为什么推翻 v2 的「三轴不加权」——
作者的判词:三个分不如一个分好判。尤其「AI 味没了、也通顺、但把原意改坏了」
这种,必须一票否决式扣大分,不能让它靠另外两项混及格。所以 v3 合成一个 0-100
的统一分:

    统一分 = 保真系数 × (0.65 × 通顺分 + 0.35 × 残留分)

    保真系数(乘在最外层,主导一切):
        绿 1.0  原意/数字/谓词方向/承诺/场景都没动,只是说顺了
        黄 0.85 轻微程度/语气/用词偏差,信息还在
        橙 0.60 丢了信息 / 局部曲解,但没凭空加东西(过度压缩也算这一档)
        红 0.30 编了原文没有的数字/承诺/场景,或把原意改反 —— 一票否决,压到 30 上下
    通顺分:顺 100 / 硬 75 / 不通顺 50
    残留分:纯正则,机器数 AI 味残留(0-100)

保真是乘法闸,所以「红」把通顺满分+残留满分也压到 ≈30;真实性权重天然最高。
0.65/0.35 让通顺压过 AI 味。这就是人工评语体现的排序:真实性 > 流畅度 > AI味。

—— 用法 ——
  # 单段只算残留(机器能独立算的部分)
  echo "一段中文" | python3 scorer_v3.py

  # 算统一分:残留机器算,保真/通顺由大模型或人给档(在线评测时大模型填)
  python3 scorer_v3.py --unified --rewrite 改写.txt --fid 黄 --flu 顺

  # 代入 50 例做校准(用人工评语标注的保真/通顺档),打印分数表 + 自洽性检查
  python3 scorer_v3.py --calibrate cases.json --labels labels.json
"""
import re, sys, json, argparse, os

# ================= 轴1:残留分(正则,机器给分) =================
# 破折号不再一律硬扣。中文本来就有破折号(维基/官媒都有规范用法),问题是「滥用+用错」。
# 机器判不了它前后通不通,所以只标「疑似,需人念」低分提示,不当硬伤——呼应 #43 排比破折号
# 人工判「原文都还行」、#36 破折号误用才该换「但是」。
#
# 【风格签名豁免(score_residual 的 style 参数)】声明名家风格(鲁迅/王小波…)时,
# 破折号、三连、分号排比这些「疑似(maybe=True)」节奏信号是名家的签名笔法,机器数不出
# 通不通,原本就只是「疑似」提示,所以在指定风格下豁免这一档扣分,避免误杀。
# ⚠️ 但「零容忍(zero=True)」硬病永不豁免:翻译腔、翻案体「不是X是Y」、半角标点、
# 元话语——呼应 haohao-shuohua SKILL.md 软硬边界「风格只能盖中性缺省口味,盖不了硬病红线」。
# 这也解释了为什么「余华」不是好风格档:他的叙事签名恰好压在翻案体这条硬病上,豁免不掉。
RESIDUAL_RULES = [
    ("章节序号/量词标题", re.compile(r'(^|\n)#{0,6}\s*([一二三四五六七八九十]+[、.]|第[一二三四五六七八九十0-9]+[章节、]|其[一二三四五六七八九十]|第[一二三四五六七八九十0-9]+[步刀条个板斧维度方面]|[一二三四五六七八九十0-9]+[刀步条板斧维度])'), 10, True, False),
    ("B2不是X是Y/翻案体", re.compile(r'(不是[^，。；\n]{1,30}[，,](而)?是[^，。\n]{1,30}|这不是[^，。\n]{1,30}|管的是[^，。\n]{1,20}不管|不在[^，。\n]{1,15}[，,]?而(在|是)|你以为[^，。\n]{1,30}[，,]?其实|(看似|表面上)[^，。\n]{1,30}[，,]?实则|回头才(发现|明白)|真正[^，。\n]{1,20}的是|不重要[，,]重要的是)'), 8, True, False),
    ("元话语", re.compile(r'(值得深思|值得关注|值得玩味|不禁让人|引人深思|发人深省|令人深思|不禁要问)'), 8, True, False),
    ("中文夹半角标点", re.compile(r'[一-鿿][,;:]|[一-鿿],(?=[^0-9])|[一-鿿]\.(?=[^0-9])'), 6, True, False),
    ("破折号——(疑似需人念)", re.compile(r'——'), 5, False, True),
    ("谄媚垫话", re.compile(r'(好问题|很好的问题|很有价值的观点|您说得对|说得太对|希望[^，。\n]{0,10}(有所帮助|帮到你|对(您|你))|期待您的|非常感谢您)'), 6, False, False),
    ("段末拔高/口号", re.compile(r'(综上所述|由此可见|不难看出|永远在路上|未来可期|书写[^，。\n]{0,8}篇章|受益终身|方能致远|砥砺前行|再创辉煌|保驾护航|谱写|新的篇章)'), 5, False, False),
    ("万能动词", re.compile(r'(进行[了]?[一了次系统全面]{0,4}[的]?[一-鿿]{0,8}(优化|调整|重构|梳理|分析|评估|处理|升级|改造|设计|完善|推进|覆盖)|作出[了]?[一-鿿]{0,6}(调整|改进|完善|贡献)|加以[一-鿿]{1,4}|予以[一-鿿]{1,4}|(对|将对)[一-鿿]{1,14}(进行|作出|实现|完成)[了]?)'), 4, False, False),
    ("名词化(对X的Y)", re.compile(r'对[一-鿿]{2,14}的(构建|优化|提升|打通|达成|梳理|完善|升级|改造|自动化|认知|理解|挖掘|支撑|完善与|重新定义)'), 3, False, False),
    ("谄媚/寒暄", re.compile(r'(非常荣幸|衷心感谢|多多关照|请您放心|祝您|亲[，,！!]|大家好[！!]|废话不多说|尽自己的一份力|贡献自己的|感谢每一位|感谢各位)'), 4, False, False),
    ("后缀病(化/性)", re.compile(r'(系统性|针对性|多样化|全方位|系统化|结构化|规范化|智能化|标准化|一体化|精细化|可扩展性|稳定性和[一-鿿]{2,6}性)'), 3, False, False),
    ("三连罗列(疑似)", re.compile(r'[一-鿿]{1,10}、[一-鿿]{1,10}、[一-鿿]{1,10}'), 4, False, True),
    ("作为开头", re.compile(r'(^|\n|。)\s*作为[一-鿿]'), 3, False, False),
    ("强调副词堆", re.compile(r'(极其|务必|绝对|必将|一定会|尽快|尽早|高度重视|诚挚地?邀请|不容错过)'), 3, False, False),
    # ↓↓↓ 新增:公文型/抒情型 AI 味(裸稿虚高的主因,50条验证过) ↓↓↓
    ("排比连接词", re.compile(r'首先[，,]|其次[，,]|再次[，,]|(^|[，。；\n])然后[，,]|最后[，,](?=[我这团为经全整])|一方面|另一方面|与此同时|总而言之'), 4, False, False),
    ("拔高套话", re.compile(r'显著(地|的)?(提|增|改|降|下降|好转)|大幅(度)?(提|降|优|改)|进一步(提|优|完善|推进|加强|深化|夯实)|深入(推进|开展|挖掘)|全面(提升|覆盖|升级)|扎实(推进|开展)|稳步(推进|提升)|有效(地)?(提升|降低|保障|支撑)'), 4, False, False),
    ("空话名词", re.compile(r'坚实(的)?基础|重要(的)?意义|良好(的)?(局面|开端|态势|基础)|有力(的)?(支撑|保障)|积极(的)?(作用|影响|意义)|长足(的)?(进步|发展)|夯实[了]?[一-鿿]{0,6}基础'), 5, False, False),
    ("成效套话", re.compile(r'(得到|取得|获得|实现)了?[一-鿿]{0,6}(提升|提高|改善|优化|突破|进展|成效|成果|飞跃)|(交付|服务|响应|工作)能力(得到|有了|实现)'), 4, False, False),
    ("为X奠定", re.compile(r'为[一-鿿]{2,14}(打下|奠定|夯实|提供了坚实|创造了良好)'), 5, False, False),
    ("文言公文腔", re.compile(r'前者|后者|(采用|决定)?上述|该(决议|方案|文档|决定|事项|决策)|自即日起|得以被|旨在(提升|打造|实现)|之所在|基石所在'), 4, False, False),
    ("分号排比句", re.compile(r'[一-鿿][，,](是|有|要|能)[^；\n]{2,20}；[一-鿿][，,](是|有|要|能)|无论[^，。\n]{2,15}[，,][他她它我们你]{1,2}(总能|都能|都会)[^。\n]{0,10}[；;]|[一-鿿]{2,8}[，,][一-鿿]{2,8}；[一-鿿]{2,8}[，,][一-鿿]{2,8}'), 5, False, True),
    ("四字成语堆", re.compile(r'(定海神针|先锋战士|迎难而上|使命必达|砥砺前行|不忘初心|勇往直前|再接再厉|继往开来|开拓创新|锐意进取|前程似锦|后会有期|江湖再见)'), 4, False, False),
]
BASE = 100
# 被字句:1-2个正常,≥3个是滥用被动(AI偏好),阶梯扣
RX_BEI = re.compile(r'被[一-鿿]')

def score_residual(text, style=None):
    """style: 指定名家风格名(如 '鲁迅'/'王小波')时,豁免「疑似(maybe=True)」类的
    节奏信号扣分——破折号、三连、分号排比这些本就是名家的签名笔法,机器判不了
    前后通不通,原本就只标「疑似,需人念」。**硬病(零容忍)永不豁免**:翻译腔、
    翻案体「不是X是Y」这类,呼应 SKILL.md 软硬边界——风格只能盖「中性缺省口味」,
    盖不了「硬病红线」。所以 style 只关掉 maybe 档的机器误伤,零容忍照扣。"""
    total, detail = 0, []
    for name, rx, per, zero, maybe in RESIDUAL_RULES:
        n = len(rx.findall(text))
        if n:
            # 风格签名豁免:声明名家风格时,只豁免「疑似」类节奏信号,零容忍硬病照扣
            exempt = bool(style) and maybe and not zero
            pen = 0 if exempt else n * per
            total += pen
            samples = []
            for m in rx.finditer(text):
                s = m.group(0).strip()
                if s and s not in samples: samples.append(s)
                if len(samples) >= 3: break
            detail.append({"类别": name, "命中数": n, "小计": pen,
                           "零容忍": zero, "疑似": maybe, "样本": samples,
                           "风格豁免": exempt})
    # 被字句阶梯:≥3个才扣,每个4分
    nb = len(RX_BEI.findall(text))
    if nb >= 3:
        pen = nb * 4
        total += pen
        detail.append({"类别": "被字句滥用(≥3)", "命中数": nb, "小计": pen,
                       "零容忍": False, "疑似": False,
                       "样本": [m.group(0) for m in list(RX_BEI.finditer(text))[:3]]})
    # 密度惩罚:全文命中总数 >5,超出部分每处 +3(呼应"某段命中超5处整段重写"红线)
    # 风格豁免掉的命中不计入密度(否则名家签名笔法会把密度顶穿,等于没豁免干净)
    total_hits = sum(d["命中数"] for d in detail if not d.get("风格豁免"))
    if total_hits > 5:
        dens = (total_hits - 5) * 3
        total += dens
        detail.append({"类别": "AI味密度惩罚(命中>5)", "命中数": total_hits, "小计": dens,
                       "零容忍": False, "疑似": False, "样本": [f"共{total_hits}处命中"]})
    detail.sort(key=lambda d: -d["小计"])
    return max(0, BASE - total), detail

# ================= 新数字预筛(归一化后再判,别误伤) =================
# 人工评语提醒:50% 和「一半」、阿拉伯数字和中文数字,可能是一个意思。改数字有时是对的、
# 更通顺的。所以这一层先把中文数字/口语量词归一化,再看是不是真冒出了原文没有的量化断言;
# 命中也只是「抬高保真怀疑,送大模型/人复核」,不自动判红,更不是硬扣分。
_CN_NUM = {'零':0,'一':1,'两':2,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
_NUM = re.compile(r'\d+(?:\.\d+)?')

def _normalize_quant(text):
    """把文本里的**量化断言**归一化成一个集合。只收真正的量化信号:
    阿拉伯数字、百分比、'一半/减半'=0.5、以及「中文数字+度量单位」(如 三倍/两秒/五分钟)。
    ⚠️ 裸中文数字(一下、三大、两个、第一)是普通措辞,不是量化断言,一律不收——防误伤。"""
    s = set()
    # 阿拉伯数字
    for m in _NUM.findall(text):
        s.add(str(float(m)))
    # 百分比归一到小数
    for m in re.findall(r'(\d+(?:\.\d+)?)\s*%|百分之([一二三四五六七八九十百]+|\d+)', text):
        raw = m[0] or m[1]
        try:
            v = float(raw) if re.match(r'^\d', raw) else _cn2int(raw)
            s.add(str(round(v/100, 4)))
        except Exception:
            pass
    # 「一半 / 减半 / 折半 / 对半」= 0.5
    if re.search(r'一半|减半|折半|对半', text): s.add('0.5')
    # 中文数字 **必须紧跟精确度量单位** 才算量化断言(倍/秒/毫秒/分钟/小时/成)
    #   —— 只收可测的性能/比例指标;排除 个/大/名/条/次/天/周/月/年 这类普通量词与
    #      泛时间词,避免「三大核心」「再发一次」「加班一周」误伤
    for num, unit in re.findall(r'([零一两二三四五六七八九十]{1,3})(倍|毫秒|秒|分钟|小时|成)', text):
        v = _cn2int(num)
        if v is not None: s.add(f"{v}{unit}")
    return s

def _cn2int(t):
    if t in _CN_NUM: return _CN_NUM[t]
    if t == '十': return 10
    if '十' in t:
        a, _, b = t.partition('十')
        hi = _CN_NUM.get(a, 1) if a else 1
        lo = _CN_NUM.get(b, 0) if b else 0
        return hi*10 + lo
    return None

# 模糊量词:出现这些说明是「大概、约数」,改写换个约数不算臆造
_FUZZY = re.compile(r'(几|多|左右|上下|来|大概|大约|约|差不多|不少|一些|许多|好几)')

def new_number_prescreen(orig, rewrite):
    """返回 (是否抬旗, 说明)。归一化后,改写里出现原文没有、且不是约数的硬量化断言,才抬旗。"""
    o, r = _normalize_quant(orig), _normalize_quant(rewrite)
    new = sorted(r - o)
    # 纯数字型新增(不带单位)且改写是模糊量化语境、原文本无数字 → 判为通顺化,不抬旗
    pure_num = [x for x in new if re.match(r'^-?\d+(\.\d+)?$', x)]
    if new and _FUZZY.search(rewrite) and not _NUM.search(orig) and not pure_num:
        return False, f"改写含约数 {new},但语境是模糊量化,判为通顺化不抬旗"
    if new:
        return True, f"新增量化 {new},原文归一化后没有 —— 臆造硬信号,送大模型/人复核(保真候选红)"
    return False, "无新增硬量化断言(已按中文/阿拉伯/百分比/一半/带单位归一化)"

# ================= 合成:一个统一分 =================
# 下列档位系数/权重不是拍的,是 fit_weights.py 用 50 条人工评语 pairwise 拟合的
# (见 data/fitted_weights.json)。要改先重跑拟合 + 全量回归,别手改。
FID = {'绿': 1.0, '黄': 0.921, '橙': 0.7193, '红': 0.2967}
FLU = {'顺': 100, '硬': 81.36, '不通顺': 50.67}
W_FLU, W_RES = 0.7157, 0.2843   # 通顺 > AI味,w 由拟合得出

def unified_score(fid, flu, residual):
    """fid∈{绿黄橙红}  flu∈{顺硬不通顺}  residual∈[0,100] → 一个 0-100 分"""
    inner = W_FLU * FLU[flu] + W_RES * residual
    return round(FID[fid] * inner, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unified", action="store_true")
    ap.add_argument("--rewrite"); ap.add_argument("--orig")
    ap.add_argument("--fid"); ap.add_argument("--flu")
    ap.add_argument("--calibrate"); ap.add_argument("--labels")
    ap.add_argument("--style", help="声明名家风格(如 鲁迅/王小波),豁免疑似类节奏信号,硬病照扣")
    a = ap.parse_args()

    if a.calibrate:
        run_calibration(a.calibrate, a.labels); return

    if a.unified and a.rewrite:
        r = open(a.rewrite, encoding="utf-8").read()
        res, _ = score_residual(r, style=a.style)
        fid = a.fid or '绿'; flu = a.flu or '顺'
        sc = unified_score(fid, flu, res)
        stag = f" | 风格 {a.style}(疑似类豁免)" if a.style else ""
        print(f"残留分 {res}/100 | 保真 {fid} | 通顺 {flu}{stag} → 统一分 {sc}/100")
        if a.orig:
            flag, msg = new_number_prescreen(open(a.orig,encoding='utf-8').read(), r)
            print(f"新数字预筛: {'⚑抬旗' if flag else '未抬旗'} — {msg}")
        return

    txt = sys.stdin.read()
    sc, det = score_residual(txt, style=a.style)
    print(f"残留分 {sc}/100" + (f" (风格 {a.style} 疑似类豁免)" if a.style else ""))
    for d in det:
        tag = "‼零容忍" if d["零容忍"] else ("?疑似" if d["疑似"] else "·症状")
        ex = " [风格豁免]" if d.get("风格豁免") else ""
        print(f"  [{tag}] {d['类别']}: {d['命中数']}处 = -{d['小计']}{ex}  例: {' / '.join(d['样本'])}")

# ---------- 校准运行器 ----------
def run_calibration(cases_path, labels_path):
    cases = json.load(open(cases_path, encoding="utf-8"))
    labels = json.load(open(labels_path, encoding="utf-8"))
    tools = ["我们", "工具1", "工具2"]
    rows, agree, total = [], 0, 0
    print(f"{'#':>3} {'文体':<8} " + "".join(f"{t:>18}" for t in tools) + "   人工判词里的赢家")
    print("-"*96)
    for it in cases:
        cid = str(it["id"])
        lab = labels.get(cid, {})
        cell, scores = {}, {}
        for t in tools:
            txt = it.get(t, "") or ""
            res, _ = score_residual(txt)
            f = lab.get(t, {}).get("f", "绿")
            l = lab.get(t, {}).get("l", "顺")
            sc = unified_score(f, l, res)
            scores[t] = sc
            cell[t] = f"{sc:>5}({f}{l[:1]}R{res})"
        winner = lab.get("winner", "")
        # 自洽性检查:人工评语说谁更好,谁的分是否最高(或并列最高)
        top = max(scores.values())
        top_tools = [t for t in tools if scores[t] >= top - 3]  # 3分容差算并列
        ok = ""
        if winner:
            total += 1
            if winner in ("平", "都差不多", "都不行"):
                # 差不多类:分差应在 ~15 内
                if max(scores.values()) - min(scores.values()) <= 15:
                    agree += 1; ok = "✓齐平"
                else: ok = "✗差距过大"
            elif "|" in winner:
                # 并列赢家:人工评语说 A、B 都好(C 最差)。要求 A、B 都进 top,且都明显高于第三方
                co = winner.split("|")
                others = [t for t in tools if t not in co]
                if all(w in top_tools for w in co) and (not others or min(scores[w] for w in co) >= max(scores[o] for o in others)):
                    agree += 1; ok = "✓并列"
                else: ok = f"✗(最高是{top_tools})"
            else:
                if winner in top_tools: agree += 1; ok = "✓"
                else: ok = f"✗(最高是{top_tools})"
        print(f"{cid:>3} {it['文体']:<8} " + "".join(f"{cell[t]:>18}" for t in tools) + f"   {winner} {ok}")
        rows.append({"id": cid, "文体": it["文体"], **scores, "winner": winner, "check": ok})
    print("-"*96)
    for t in tools:
        vals = [r[t] for r in rows]
        print(f"{t} 均分 {sum(vals)/len(vals):.1f}  最低 {min(vals)}  最高 {max(vals)}")
    print(f"\n自洽性:有明确人工判词的 {total} 例中,尺子排序一致 {agree} 例 ({agree/max(1,total)*100:.0f}%)")
    # 技能目录只读,校准结果写到当前工作目录
    out_path = os.path.join(os.getcwd(), "calib_scores.json")
    json.dump(rows, open(out_path,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"写出 {out_path}")

if __name__ == "__main__":
    main()
