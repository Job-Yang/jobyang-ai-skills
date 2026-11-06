#!/usr/bin/env bash
# me-context v4 自测：fail-closed 安全默认 + 负面反例全覆盖。set -euo pipefail。
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PY=python3
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
expect_rc() { # $1=期望退出码，其余=命令
  want="$1"; shift
  out="$("$@" 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -eq "$want" ]; then ok "rc=$want  $*"; else bad "期望 rc=$want 实得 rc=$rc  命令:$*"; echo "$out"; fi
  LAST="$out"
}
expect_grep0() { # $1=pattern $2=file
  c=$(grep -c "$1" "$2" 2>/dev/null || true)
  if [ "$c" -eq 0 ]; then ok "敏感串『$1』在 $(basename "$2") 出现 0 次"; else bad "敏感串『$1』出现 $c 次（应 0）"; fi
}

WORK="$(mktemp -d)"; cp -R "$HERE/examples/." "$WORK/"
rm -rf "$WORK/exports"

echo "== 1) init 空白临时仓 =="
TMP="$HERE/_selftest_tmp"; rm -rf "$TMP"
expect_rc 0 $PY "$HERE/scripts/init.py" --path "$TMP"
{ [ -f "$TMP/network.md" ] && [ -d "$TMP/inbox" ]; } && ok "init 铺 network.md + inbox/" || bad "init 缺 network.md/inbox"
{ [ -f "$TMP/profile/body.md" ]; } && ok "init 铺 body.md" || bad "init 缺 body.md"
expect_rc 0 $PY "$HERE/scripts/lint.py" --data "$TMP" && ok "全新 init 仓 lint 通过(body.md 合法)" || bad "init 仓 lint 失败"

echo "== 2) lint 干净 examples 应 PASS=0 =="
expect_rc 0 $PY "$HERE/scripts/lint.py" --data "$HERE/examples"

echo "== 3) lint neg 应 FAIL=1（无头部/缺结尾---/错位L4） =="
expect_rc 1 $PY "$HERE/scripts/lint.py" --data "$HERE/tests/fixtures/neg"
echo "$LAST" | grep -q "bad-nofm" && ok "lint 报无头部" || bad "未报无头部"
echo "$LAST" | grep -q "bad-noend" && ok "lint 报缺结尾---" || bad "未报缺结尾---"
echo "$LAST" | grep -q "wrongplace-l4" && ok "lint 报错位 L4" || bad "未报错位 L4"

echo "== 4) gate 未知 domain 应 rc=1 =="
expect_rc 1 $PY "$HERE/scripts/gate.py" --data "$WORK" --domain family --audience cloud

echo "== 5) 任务分类：医疗行业投资→finance；失眠→health；多域标注 =="
out=$($PY "$HERE/scripts/gate.py" --data "$WORK" --task "分析医疗行业投资机会" 2>&1) || true
echo "$out" | grep -q "建议 domain=finance" && ok "医疗行业投资归 finance" || bad "未归 finance"
echo "$out" | grep -q "多域命中" && ok "多域命中已标注" || bad "未标注多域"
out=$($PY "$HERE/scripts/gate.py" --data "$WORK" --task "最近失眠头疼怎么办" 2>&1) || true
echo "$out" | grep -q "建议 domain=health" && ok "失眠头疼归 health" || bad "失眠未归 health"

echo "== 6) gate cloud 触达 L3 未 --confirm：rc=2 且 stdout 无 L3 内容 =="
out=$($PY "$HERE/scripts/gate.py" --data "$WORK" --domain health --audience cloud --emit 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 2 ] && ok "L3 未 confirm rc=2" || bad "L3 未 confirm rc=$rc"
echo "$out" | grep -q "高血压" && bad "未 confirm 却输出 L3" || ok "未 confirm 未输出 L3 内容"

echo "== 7) gate --confirm --emit：rc=0，包裹头存在，切片含 health =="
out=$($PY "$HERE/scripts/gate.py" --data "$WORK" --domain health --audience cloud --confirm --emit) && rc=0 || rc=$?
[ "$rc" -eq 0 ] && ok "--confirm --emit rc=0" || bad "rc=$rc"
echo "$out" | grep -q "^<me-context-data>" && ok "包裹头 <me-context-data> 存在" || bad "缺包裹头"
echo "$out" | grep -q "高血压" && ok "--confirm 后输出 L3 内容" || bad "confirm 后仍无 L3"

echo "== 8) gate L4 任意参数 rc=3 不输出内容 =="
expect_rc 3 $PY "$HERE/scripts/gate.py" --data "$WORK" --domain work --layer L4 --audience cloud --emit

echo "== 9) export 默认 md：rc=0，敏感串全 0，不含 network(L2) =="
MD1="$WORK/exports/d1.md"; mkdir -p "$WORK/exports"
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$WORK" --out "$MD1"
for s in 高血压 糖尿病 心脏病 银行卡密码; do expect_grep0 "$s" "$MD1"; done
grep -q "文件：network.md" "$MD1" && bad "默认 md 含 network(L2) 文件块" || ok "默认 md 不含 network(L2) 文件块"

echo "== 10) export --all-layers：含 network.md 概览与 health(L3) =="
MD2="$WORK/exports/d2.md"
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$WORK" --all-layers --out "$MD2"
grep -q "文件：network.md" "$MD2" && ok "--all-layers 含 network.md 文件块" || bad "--all-layers 缺 network"
grep -q "高血压" "$MD2" && ok "--all-layers 含 L3 health" || bad "--all-layers 缺 health"

echo "== 11) export fail-closed：work.md 去头部后默认导出应 rc=1 =="
awk 'BEGIN{c=0} /^---$/{c++; if(c<=2){next}} {print}' "$HERE/examples/profile/work.md" > /tmp/work_nofm.md
cp /tmp/work_nofm.md "$WORK/profile/work.md"
expect_rc 1 $PY "$HERE/scripts/export.py" --data "$WORK" --out "$WORK/exports/d3.md"
echo "$LAST" | grep -q "fail-closed" && ok "fail-closed 报错列出未分级" || bad "未报 fail-closed"
echo "== 11b) --include-unclassified 后 rc=0 且产物标注含未分级 =="
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$WORK" --out "$WORK/exports/d4.md" --include-unclassified
grep -q "含未分级内容" "$WORK/exports/d4.md" && ok "产物头部标注含未分级" || bad "未标注"
cp "$HERE/examples/profile/work.md" "$WORK/profile/work.md"

echo "== 12) zip 默认：敏感串 0、无 private/、不含 L4 =="
Z1="$WORK/b1.zip"
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$WORK" --format zip --out "$Z1"
UNZ="$(mktemp -d)"; unzip -q "$Z1" -d "$UNZ"
[ -f "$UNZ/private/secret.md" ] && bad "默认 zip 含 private/" || ok "默认 zip 不含 private/"
grep -rq "银行卡密码" "$UNZ" && bad "默认 zip 含 L4 银行卡密码" || ok "默认 zip 不含 L4 银行卡密码"

echo "== 13) zip --include-private：含 private/secret =="
Z2="$WORK/b2.zip"
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$WORK" --format zip --out "$Z2" --include-private
UNZ2="$(mktemp -d)"; unzip -q "$Z2" -d "$UNZ2"
[ -f "$UNZ2/private/secret.md" ] && ok "--include-private 含 private/secret" || bad "--include-private 缺 private"

echo "== 14) gate network：不整份加载 peripheral，不读 inbox =="
out=$($PY "$HERE/scripts/gate.py" --data "$HERE/examples" --domain network --audience local 2>&1)
echo "$out" | grep -q "entities/barber-liu" && bad "network 整份加载 peripheral" || ok "network 不整份 peripheral"
echo "$out" | grep -q "机械键盘" && bad "gate 读到了 inbox 草稿内容" || ok "gate 不读 inbox 草稿内容"
echo "== 14b) [v16] network.md 标 audience: local：外发未确认 HOLD，确认后才放行 =="
out=$($PY "$HERE/scripts/gate.py" --data "$HERE/examples" --domain network --audience cloud --emit 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 2 ] && ok "audience:local 外发未确认 rc=2" || bad "audience:local 外发 rc=$rc（应 2）"
echo "$out" | grep -q "^<me-context-data>" && bad "未确认却输出了正文" || ok "未确认不输出正文"
echo "$out" | grep -q "只在本机用" && ok "HOLD 说明点名了只在本机的文件" || bad "HOLD 未说明原因"
out=$($PY "$HERE/scripts/gate.py" --data "$HERE/examples" --domain network --audience cloud --confirm --emit 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 0 ] && ok "确认后 rc=0" || bad "确认后 rc=$rc"
out=$($PY "$HERE/scripts/gate.py" --data "$HERE/examples" --domain work --audience cloud --emit 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 0 ] && ok "cloud-low 的 work 外发不受影响 rc=0" || bad "work 外发被误拦 rc=$rc"

echo "== 15) [P0] 默认 zip 排除破头 L4 / 未分级 / symlink =="
NZ="$WORK/n.zip"
expect_rc 4 $PY "$HERE/scripts/export.py" --data "$HERE/tests/fixtures/neg" --format zip --out "$NZ"
UNZN="$(mktemp -d)"; unzip -q "$NZ" -d "$UNZN"
grep -rq "破头L4秘密RT" "$UNZN" && bad "默认 zip 含破头 L4" || ok "默认 zip 排破头 L4"
grep -rq "relationsL4测试串" "$UNZN" && bad "默认 zip 白名单短路收 L4 relations" || ok "白名单 relations 标 L4 仍被默认排"
grep -rq "无头部秘密\|缺结尾秘密" "$UNZN" && bad "默认 zip 含未分级 md" || ok "默认 zip 排未分级 md"
grep -rq "仓外秘密RT" "$UNZN" && bad "默认 zip 跟随 symlink 带出仓外" || ok "默认 zip 不跟 symlink"
grep -rq "private/secret" "$UNZN" && bad "默认 zip 含 private" || ok "默认 zip 排 private"

echo "== 16) [P0] zip 三档：unclassified 纳未分级但仍排嗅探L4；private 才含 L4；退出码 =="
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HERE/tests/fixtures/neg" --format zip --out "$WORK/n2.zip" --include-unclassified
UNZN2="$(mktemp -d)"; unzip -q "$WORK/n2.zip" -d "$UNZN2"
grep -rq "上面没有结尾" "$UNZN2" && ok "include-unclassified 纳入普通未分级(bad-noend)" || bad "include-unclassified 未纳入"
grep -rq "破头L4秘密RT" "$UNZN2" && bad "unclassified 却纳入嗅探L4" || ok "unclassified 仍排嗅探L4(破头)"
expect_rc 4 $PY "$HERE/scripts/export.py" --data "$HERE/tests/fixtures/neg" --format zip --out "$WORK/n3.zip" --include-private
UNZN3="$(mktemp -d)"; unzip -q "$WORK/n3.zip" -d "$UNZN3"
[ -f "$UNZN3/private/secret.md" ] && ok "include-private 含 private" || bad "include-private 缺 private"
grep -rq "relationsL4测试串" "$UNZN3" && ok "include-private 收白名单L4 relations" || bad "include-private 缺 relationsL4"

echo "== 17) [P2-1] md --include-l4 真正纳入 private L4，默认不含 =="
MDL4="$WORK/l4.md"
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HERE/examples" --out "$MDL4" --include-l4
grep -q "888888" "$MDL4" && ok "--include-l4 含 private L4(888888)" || bad "--include-l4 未含 L4"
grep -q "禁止上传云端" "$MDL4" && ok "产物头标禁止外发" || bad "缺禁止外发标注"
grep -q "888888" "$WORK/exports/d1.md" && bad "默认 md 含 L4" || ok "默认 md 不含 L4"

echo "== 18) [P1-3] 空仓 gate 不 traceback =="
EMPTY="$(mktemp -d)"
out=$($PY "$HERE/scripts/gate.py" --data "$EMPTY" --domain health --emit 2>&1) && rc=0 || rc=$?
echo "$out" | grep -q "Traceback" && bad "空仓 gate 打 traceback" || ok "空仓无 traceback"
[ "$rc" -eq 0 ] && ok "空仓 exit 0 友好零切片" || bad "空仓 rc=$rc"

echo "== 19) [P2-2] --layer 空串按未提供处理 =="
out=$($PY "$HERE/scripts/gate.py" --data "$HERE/examples" --domain work --layer "   " 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 0 ] && ok "--layer 空串回落域默认 rc=0" || bad "--layer 空串 rc=$rc"

echo "== 20) [v5 P2] 过敏路由 health L3；bootstrap 口语区无内部术语 =="
grep -qiE "过敏|青霉素|慢病|长期用药" "$HERE/templates/profile/preferences.md" "$HERE/examples/profile/preferences.md" \
  && bad "preferences 收了过敏类词(应路由 health L3)" || ok "preferences 不收过敏类词"
grep -qE "过敏路由.*health|任意模块.*health L3" "$HERE/references/02-question-architecture.md" \
  && ok "02 含过敏→health L3 路由规则" || bad "02 缺过敏路由硬规则"

echo "== 21) [v6] 用户可见模板/示例无量表标签与工程诱导词；05 有 scope 分流 =="
HITS=$(grep -rlE "GDMS|DOSPERT|RIASEC|risk\.opt_in|rational|intuitive|avoidant|风格.?hint" \
  "$HERE/templates/profile/decisions.md" "$HERE/templates/profile/finance.md" \
  "$HERE/examples/profile/decisions.md" "$HERE/examples/profile/finance.md" 2>/dev/null || true)
[ -z "$HITS" ] && ok "decisions/finance 模板与示例无 GDMS/DOSPERT/risk.opt_in 残留" || bad "量表标签残留: $HITS"
grep -qE "scope: general\|engineering|工程.*不放进个人档案|分流" "$HERE/references/05-write-protocol.md" \
  && ok "05 含 scope 分流规则" || bad "05 缺 scope 分流"
# scope 可选：无 scope 的正式文件 lint 不因此报错
expect_rc 0 $PY "$HERE/scripts/lint.py" --data "$HERE/examples"

echo "== 22) [v6 P2] inbox 工程草稿 scope 启发式（WARN 但 rc=0；正式 profile 不扫）=="
T="$WORK/inboxscope"; rm -rf "$T"; mkdir -p "$T/inbox"
cp "$HERE/examples/ME.md" "$T/ME.md"
cat > "$T/inbox/draft-noscope.md" <<'EOF'
---
status: draft
source: observed
---
commit 前必须跑测试
EOF
out=$($PY "$HERE/scripts/lint.py" --data "$T" 2>&1); rc=$?
echo "$out" | grep -q "scope: engineering" && ok "无 scope 工程草稿触发启发式 WARN" || bad "缺启发式 WARN"
[ "$rc" -eq 0 ] && ok "WARN 不影响 lint rc=0" || bad "启发式误升 rc=$rc"
cat > "$T/inbox/draft-noscope.md" <<'EOF'
---
status: draft
source: observed
scope: engineering
---
commit 前必须跑测试
EOF
out=$($PY "$HERE/scripts/lint.py" --data "$T" 2>&1)
echo "$out" | grep -q "scope: engineering" && bad "显式 engineering 仍重复 WARN" || ok "显式 engineering 不重复 WARN"

echo "== 23) [v7] T0/T1/T2 信任梯度 + 访谈形态 + check_questions 正反例 =="
# a) 真题本 check_questions exit 0
expect_rc 0 $PY "$HERE/scripts/check_questions.py" --questions "$HERE/templates/questions/bootstrap.md"
# b) 坏题本（快速档问收入 + 一次三题编号）check_questions exit 非0
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$HERE/tests/fixtures/neg/bad-questions.md"
# c) 执行说明含访谈形态硬规则
grep -q "T0 低敏/半公开（称呼、城市" "$HERE/templates/questions/bootstrap.md" && ok "执行说明含 T0 高效成组分层节奏" || bad "缺 T0 成组分层"
grep -q "禁止自报模块进度" "$HERE/templates/questions/bootstrap.md" && ok "禁止自报模块进度" || bad "缺禁进度"
grep -q "先接话" "$HERE/templates/questions/bootstrap.md" && ok "含'先接话再过渡'" || bad "缺先接话"
grep -q "不用 1/2/3 编号列表" "$HERE/templates/questions/bootstrap.md" && ok "禁编号列表抛出" || bad "缺禁编号"
# c2) [v13] 禁止播报内部过程：题本含该纪律 + 反例句式 + SKILL 6.5
grep -q "只对用户讲有价值的话" "$HERE/templates/questions/bootstrap.md" && ok "题本含'不讲内部过程'纪律" || bad "缺不讲内部过程纪律"
grep -q "体检脚本 14 个文件零报错" "$HERE/templates/questions/bootstrap.md" && ok "题本含内部播报反例" || bad "缺内部播报反例"
grep -q "6.5 对用户只讲有价值的话" "$HERE/SKILL.md" && ok "SKILL 含 6.5 不播报内部过程" || bad "SKILL 缺 6.5"
# d) 05/SKILL 含 T2 触发三条件 + 禁止自动推进
grep -qE "T2 触发三条件|当次任务显式需要" "$HERE/references/05-write-protocol.md" && ok "05 含 T2 触发三条件" || bad "05 缺 T2 三条件"
grep -qE "禁止建档结束后自动|召唤制" "$HERE/references/05-write-protocol.md" && ok "05 禁自动推进财务健康包" || bad "05 缺召唤制"
# e) 财务包先问目标、收入放最后可选（关键词顺序齐全即可）
grep -q "先问目标与约束" "$HERE/references/02-question-architecture.md" && ok "财务包先问目标" || bad "财务包缺先问目标"
grep -q "收入放最后且可选" "$HERE/references/02-question-architecture.md" && ok "财务包收入最后可选" || bad "财务包收入未标可选"
# f) DOMAIN_ASK_GATE 存在且 finance/health=T2、network=T1
$PY -c "import sys; sys.path.insert(0,'$HERE/scripts'); import mectx_common as C; \
assert C.DOMAIN_ASK_GATE['finance']=='T2-need-trigger'; assert C.DOMAIN_ASK_GATE['health']=='T2-need-trigger'; \
assert C.DOMAIN_ASK_GATE['network']=='T1'" \
  && ok "DOMAIN_ASK_GATE: finance/health=T2, network=T1" || bad "DOMAIN_ASK_GATE 缺失/错误"

echo "== 24) [v7 P2] ASK_GATE 接线、词表/连问/软流水线护栏、goals 去量表 =="
# g) check_questions 源码 import 并消费 DOMAIN_ASK_GATE（非另写硬编码域清单）
grep -q "DOMAIN_ASK_GATE" "$HERE/scripts/check_questions.py" && ok "check_questions import 并使用 ASK_GATE" || bad "check_questions 未接 ASK_GATE"
# h) ASK_GATE 运行时消费：把 finance 改成 T0 后，finance 敏感词不再被拦（证明常量驱动词表，改坏可感知）
$PY - "$HERE" <<'PY' && ok "ASK_GATE 漂移可感知(finance→T0 不再拦年薪)" || bad "ASK_GATE 未被运行时消费"
import sys, os, importlib
here = sys.argv[1]
sys.path.insert(0, os.path.join(here, "scripts"))
import check_questions as cq, mectx_common as C
# 构造一条含 finance 直问的可见行；默认应命中
C.DOMAIN_ASK_GATE["finance"] = "T0"  # 改坏：finance 降 T0，finance 词应不再拦截
active = {d: w for d, w in cq.DOMAIN_WORDS.items() if C.DOMAIN_ASK_GATE.get(d, C.DEFAULT_ASK_GATE) != "T0"}
assert "finance" not in active, "finance 已 T0 却仍在拦截词表"
PY
# i) goals 模板/示例无价值象限/量表残留
grep -rnE "象限|quadrant|价值取向|self-enhancement|self-transcendence|conservation|偏高|居中|偏低" \
  "$HERE/templates/profile/goals.md" "$HERE/examples/profile/goals.md" 2>/dev/null \
  && bad "goals 残留价值象限/高低分" || ok "goals 纯目标事实、无量表残留"
# j) 坏题本仍 rc=1（同义词/散文连问/软流水线全覆盖）
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$HERE/tests/fixtures/neg/bad-questions.md"

# k) 借壳豁免反例：含"以后…你年薪"与"别客气，你结婚了吗"都必须被拦，合法提示句不被误伤
$PY - "$HERE" <<'PY' && ok "借壳'以后+你年薪'被拦、'别客气+结婚'被拦、合法过敏提示句放行" || bad "借壳豁免精度回归"
import sys, os, importlib
here = sys.argv[1]; sys.path.insert(0, os.path.join(here, "scripts"))
cq = importlib.import_module("check_questions")
# 借壳1：含"以后"但是当下第二人称问句 → 不豁免
assert not cq._exempt("以后聊到再说，你年薪多少？")
# 借壳2："别客气"不是禁令短语，且是问句 → 不豁免
assert not cq._exempt("别客气，你结婚了吗？孩子几岁？")
# 合法提示句：陈述句、无"你…？"索要 → 豁免
legal = "以后你问我健康或用药问题时，我会先跟你确认过敏和在吃的药，免得给错建议；现在不用专门说。"
assert cq._exempt(legal)
PY

echo
echo "== 25) [v8] T0 高效成组分区：T0 自然成组 rc0，混敏感/编号 rc1 =="
# 构造临时题本（/tmp，不污染真题本）
RHY="$(mktemp -d)"
cat > "$RHY/t0-group.md" <<'MD'
# 快速话题地图

## 话题 1 · 基本情况（T0，建档即聊）
- 可参考切入：你在哪个城市呀？平时大概几点睡，周末一般干嘛？
# 标准档
MD
cat > "$RHY/mixed.md" <<'MD'
# 快速话题地图

## 话题 1 · 基本情况（T0）
- 可参考切入：你在哪个城市、年薪多少、血压正常吗？
# 标准档
MD
cat > "$RHY/numbered.md" <<'MD'
# 快速话题地图

## 话题 1 · 基本情况（T0）
- 可参考切入：1)城市 2)作息 3)周末干嘛
# 标准档
MD
expect_rc 0 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/t0-group.md"
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/mixed.md"
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/numbered.md"

# [v8fix] 新词表：过敏/长期吃的药/老婆/身份证手机号
cat > "$RHY/allergy.md" <<'MD'
# 快速话题地图

## 话题 1 · 健康（T0）
- 可参考切入：你对什么药物过敏？平时有没有要长期吃的药？
# 标准档
MD
cat > "$RHY/wife.md" <<'MD'
# 快速话题地图

## 话题 1 · 家庭（T1）
- 可参考切入：你老婆是做什么的？
# 标准档
MD
cat > "$RHY/idno.md" <<'MD'
# 快速话题地图

## 话题 1 · 基本（T0）
- 可参考切入：你身份证多少、手机号给我
# 标准档
MD
# [v8fix] 编号变体：圆点 1./、模块1/模块2
cat > "$RHY/dotnum.md" <<'MD'
# 快速话题地图

## 话题 1 · 基本（T0）
- 可参考切入：1.城市 2.作息 3.爱好
# 标准档
MD
cat > "$RHY/module.md" <<'MD'
# 快速话题地图

## 话题 1 · 基本（T0）
- 可参考切入：模块1：称呼，模块2：城市
# 标准档
MD
# [v8fix] 半角问号在非T0（标题缺T级→保守T1）也拦
cat > "$RHY/halfq.md" <<'MD'
# 快速话题地图

## 话题 5 · 有没有我该知道的人
- 可参考切入：家里还有什么人? 常联系吗?
# 标准档
MD
# [v8fix] T0 五问仅 WARN、rc 仍 0
cat > "$RHY/t0five.md" <<'MD'
# 快速话题地图

## 话题 1 · 基本（T0）
- 可参考切入：你在哪个城市呀？平时几点睡？周末干嘛？喜欢吃什么？怎么上下班？
# 标准档
MD
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/allergy.md"
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/wife.md"
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/idno.md"
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/dotnum.md"
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/module.md"
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/halfq.md"
expect_rc 0 $PY "$HERE/scripts/check_questions.py" --questions "$RHY/t0five.md"
grep -q "WARN" <($PY "$HERE/scripts/check_questions.py" --questions "$RHY/t0five.md" 2>&1) \
  && ok "T0 五问出 WARN 但 rc=0" || bad "T0 五问缺 WARN"
expect_rc 0 $PY "$HERE/scripts/check_questions.py" --questions "$HERE/templates/questions/bootstrap.md"
expect_rc 1 $PY "$HERE/scripts/check_questions.py" --questions "$HERE/tests/fixtures/neg/bad-questions.md"

echo
echo "== 26) [v10] viz 左导航+右档案：JSON 注入/分区渲染/分区级脱敏/中文关系/钻取/坏头/空仓 =="
VZ="$(mktemp -d)"
# ① all/profile/network × local/cloud 各 rc0；JSON 注入标记在
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$WORK" --view network --audience local --out "$VZ/net.html"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$WORK" --view profile --audience local --out "$VZ/prof.html"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$WORK" --view all --audience local --out "$VZ/all.html"
grep -q 'id="mc-data"' "$VZ/all.html" && ok "含 JSON 数据注入(mc-data)" || bad "缺 mc-data 注入"
# 三圈环带标注、四实体、中文关系胶囊在数据里
for n in 李 王工 小明 理发店; do grep -q "$n" "$VZ/net.html" && ok "network local 含实体 $n" || bad "network 缺实体 $n"; done
for ring in 核心圈 重要圈 外围圈; do grep -q "$ring" "$VZ/net.html" && ok "环带 $ring 标注" || bad "缺环带 $ring"; done
for rel in 配偶 同事 认识 子女; do grep -q "$rel" "$VZ/all.html" && ok "可见中文关系胶囊：$rel" || bad "缺中文关系 $rel"; done
# ② 外链/alert：无 src=http/href=http、无 alert(
grep -qE 'src="http|href="http' "$VZ/all.html" && bad "出现 http 外链" || ok "无 http 外链"
grep -q "alert(" "$VZ/all.html" && bad "出现 alert(" || ok "无 alert("
# ③ 交互钩子：addEventListener 节点点击、hash 路由、id 白名单正则
grep -q "addEventListener" "$VZ/all.html" && ok "addEventListener 点击处理" || bad "缺 addEventListener"
grep -q "parseHash" "$VZ/all.html" && ok "hash 路由 parseHash" || bad "缺 parseHash"
grep -q "validId" "$VZ/all.html" && grep -q "a-z0-9_-" "$VZ/all.html" && ok "hash id 白名单正则防注入" || bad "缺 id 白名单"
# local 含 L3 明文（青霉素/高血压）
grep -q "高血压" "$VZ/all.html" && ok "local 含 L3 串(高血压)" || bad "local 未渲染 L3"
grep -q "青霉素" "$VZ/all.html" && ok "local 含 L3 青霉素" || bad "local 未渲染青霉素"
# cloud：L3/L4 敏感串=0（分区级过滤：非敏感基本/职业/喜好仍在）
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$WORK" --view all --audience cloud --out "$VZ/cloud.html"
for s in 高血压 糖尿病 青霉素 坚果 心脏病 888888; do expect_grep0 "$s" "$VZ/cloud.html"; done
grep -q "导出/发给外部 AI 时默认不带出" "$VZ/cloud.html" && ok "cloud 敏感分区显锁块" || bad "cloud 缺分区锁块"
# 配偶档案标了 audience: local → cloud 整人锁（与 gate/md 一致）；没标的同事非敏感分区照常可见
grep -q "设计师" "$VZ/cloud.html" && bad "cloud 带出了标 local 的配偶职业" || ok "cloud 锁住标 local 的配偶档案"
grep -q "API 评审" "$VZ/cloud.html" && ok "cloud 同事主要事实可见" || bad "cloud 误锁同事事实"
# ④ 空数据仓 rc0 无 Traceback
EMPTY="$(mktemp -d)"
empty_out="$($PY "$HERE/scripts/viz.py" --data "$EMPTY" --view all --audience local --out "$VZ/empty.html" 2>&1)" && erc=0 || erc=$?
[ "$erc" -eq 0 ] && ok "空仓 rc=0 不崩" || bad "空仓 rc=$erc"
echo "$empty_out" | grep -q "Traceback" && bad "空仓 Traceback" || ok "空仓无 Traceback"
# ⑤ 默认 local 不展开 L4，--show-l4 才出现且有警示
grep -q "888888" "$VZ/all.html" && bad "默认 local 误展开 L4" || ok "默认 local 不展开 L4"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$WORK" --view all --audience local --show-l4 --out "$VZ/l4.html"
grep -q "888888" "$VZ/l4.html" && ok "--show-l4 展开 L4" || bad "--show-l4 未展开"
grep -q "禁止上传" "$VZ/l4.html" && ok "--show-l4 含红色 L4 警示" || bad "缺 L4 警示"
# ⑧ inbox 草稿串两种 audience 都=0
expect_grep0 "机械键盘" "$VZ/all.html"
expect_grep0 "机械键盘" "$VZ/cloud.html"
# ⑨ 坏头/缺层跳过且 rc0；relations 坏头提示；幽灵边提示
BAD="$(mktemp -d)"; cp -R "$WORK/." "$BAD/"
printf -- '---\nlayer: L1\n（缺结尾 ---）\n# 坏头\n' > "$BAD/entities/broken.md"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$BAD" --view network --audience local --out "$VZ/bad.html"
grep -q "跳过" "$VZ/bad.html" && ok "坏头在 HTML 列跳过" || bad "坏头无跳过提示"
REL="$(mktemp -d)"; cp -R "$WORK/." "$REL/"; printf -- '---\n（坏头缺结尾）\n' > "$REL/relations.md"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$REL" --view network --audience local --out "$VZ/rel.html"
grep -q "头部异常\|缺失" "$VZ/rel.html" && ok "relations 坏头有提示（非静默归零）" || bad "relations 坏头静默"
GHOST="$(mktemp -d)"; cp -R "$WORK/." "$GHOST/"
printf '\n- from: me\n  type: knows\n  to: ghost-person\n  direction: directed\n' >> "$GHOST/relations.md"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$GHOST" --view network --audience local --out "$VZ/ghost.html"
grep -q "未记录实体" "$VZ/ghost.html" && ok "幽灵边提示已跳过" || bad "幽灵边无提示"
# [local --layers 同时过滤实体] L1 层不含 L2/L3 实体
LYR="$(mktemp -d)"; cp -R "$WORK/." "$LYR/"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$LYR" --view network --audience local --layers L1 --out "$VZ/lyr.html"
for n in 王工 理发店; do expect_grep0 "$n" "$VZ/lyr.html"; done
# ME 误标 ≥L3，cloud 名片锁（me_locked 被消费）
MELOCK="$(mktemp -d)"; cp -R "$WORK/." "$MELOCK/"; sed -i '' 's/^layer: L1/layer: L3/' "$MELOCK/ME.md"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$MELOCK" --view profile --audience cloud --out "$VZ/melock.html"
grep -q "外发预览" "$VZ/melock.html" && ok "ME≥L3 cloud 名片锁" || bad "me_locked 未消费"
# ME 坏头/未分级 cloud fail-closed 占位、不泄露正文
MEBAD="$(mktemp -d)"; cp -R "$WORK/." "$MEBAD/"; printf -- '---\n（缺结尾 ---）\n- 称呼：张三\n' > "$MEBAD/ME.md"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$MEBAD" --view profile --audience cloud --out "$VZ/mebad.html"
expect_grep0 "张三" "$VZ/mebad.html"
# XSS 探针：label 走 esc()，无独立可执行 breakout
XSS="$(mktemp -d)"; cp -R "$WORK/." "$XSS/"
cat > "$XSS/entities/xss-p.md" <<'EOF'
---
schema: personal-context/v1
entity: xss-p
circle: close
layer: L2
---
- 称呼：</script><img src=x onerror=alert(1)>张三
EOF
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$XSS" --view network --audience local --out "$VZ/xss.html"
grep -q "esc(" "$VZ/xss.html" && ok "节点 label 走 esc() 转义" || bad "图 label 未转义"
grep -qc "<script>alert" "$VZ/xss.html" || ok "无独立可执行 script 突破"
# 缺 profile 文件 → rc0、占位、无 Traceback
MISS="$(mktemp -d)"; cp -R "$WORK/." "$MISS/"; rm -f "$MISS/profile/preferences.md" "$MISS/profile/body.md"
miss_out="$($PY "$HERE/scripts/viz.py" --data "$MISS" --view all --audience local --out "$VZ/miss.html" 2>&1)" && mrc=0 || mrc=$?
[ "$mrc" -eq 0 ] && ok "缺 profile 文件 rc=0 不崩" || bad "缺文件 rc=$mrc"
echo "$miss_out" | grep -q "Traceback" && bad "缺文件出现 Traceback" || ok "缺文件无 Traceback"
grep -q "还没告诉我" "$VZ/miss.html" && ok "缺文件卡显'还没告诉我'占位" || bad "缺文件无占位"
# cloud 即便 --layers L3,L4 也零 L3/L4 明文；误标 L4 的 health 也锁
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$WORK" --view all --audience cloud --layers L3,L4 --out "$VZ/cl.html"
for s in 高血压 糖尿病 青霉素 888888; do expect_grep0 "$s" "$VZ/cl.html"; done
L4D="$(mktemp -d)"; cp -R "$WORK/." "$L4D/"
sed -i '' 's/^layer: L3/layer: L4/' "$L4D/profile/health.md"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$L4D" --view all --audience cloud --out "$VZ/l4cloud.html"
for s in 高血压 糖尿病; do expect_grep0 "$s" "$VZ/l4cloud.html"; done
grep -q "不带出" "$VZ/l4cloud.html" && ok "误标L4的health在cloud显锁占位" || bad "误标L4缺锁"
# 可见文本无原始 markdown/模板占位/量表英文残留
grep -q '\*\*' "$VZ/all.html" && bad "可见文本残留 **" || ok "无原始 **"
grep -qE "rational|intuitive|avoidant|<例|<…>" "$VZ/all.html" && bad "残留模板占位/量表英文" || ok "无模板占位/量表英文"
# 立场逐字：确定性渲染、无黑盒
grep -q "确定性渲染" "$VZ/all.html" && ok "HTML 含'确定性渲染'" || bad "缺确定性渲染"
grep -q "无黑盒" "$VZ/all.html" && ok "HTML 含'无黑盒'" || bad "缺无黑盒"

# [v10.1] 事业温度标题：履历→走过的路、核心能力→擅长的事、代表项目(量化)→做成过的事；无硬词
WKT="$(mktemp -d)"; cp -R "$WORK/." "$WKT/"
cat > "$WKT/profile/work.md" <<'EOF'
---
layer: L1
---
## 一句话定位
做 AI Agent 工程。
## 履历
- 2016.09—2018.01 斑马物联网，iOS 工程师
## 核心能力
- 性能与稳定性优化
## 代表项目（量化）
- 整包近百兆，实测体积 76.7M→41M
EOF
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$WKT" --view profile --audience local --out "$VZ/wkt.html"
grep -q "走过的路" "$VZ/wkt.html" && ok "事业温度标题『走过的路』" || bad "缺温度标题 走过的路"
grep -q "擅长的事" "$VZ/wkt.html" && ok "事业温度标题『擅长的事』" || bad "缺温度标题 擅长的事"
grep -q "做成过的事" "$VZ/wkt.html" && ok "事业温度标题『做成过的事』" || bad "缺温度标题 做成过的事"
grep -q "履历" "$VZ/wkt.html" && bad "仍出现招聘硬词『履历』" || ok "无招聘硬词 履历"
grep -q "核心能力" "$VZ/wkt.html" && bad "仍出现招聘硬词『核心能力』" || ok "无招聘硬词 核心能力"
grep -q "代表项目" "$VZ/wkt.html" && bad "仍出现招聘硬词『代表项目』" || ok "无招聘硬词 代表项目"
rm -rf "$WKT"

# [v10.1] 标准空仓：无 relations 不报异常；健康/财务空卡无问号徽标、无模板说明，只显温度空态
EMPTY2="$(mktemp -d)"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$EMPTY2" --view all --audience local --out "$VZ/empty2.html"
grep -q "头部异常已跳过\|头部异常/缺层\|缺失或为符号链接" "$VZ/empty2.html" && bad "标准空仓误报跳过异常" || ok "标准空仓不误报异常"
grep -q "只防\|只记区间" "$VZ/empty2.html" && bad "空卡把模板说明当内容" || ok "空卡不显模板使用说明"
grep -qE 'lv-L3">？|badge[^>]*>？' "$VZ/empty2.html" && bad "空卡出现问号层级徽标" || ok "空卡无问号徽标(敏感=橙)"
rm -rf "$EMPTY2"

# [v10.2] P1-1 内嵌本名（称呼值里"；本名 刘凤华"）头像取"刘"，不回退成"老"
AVA="$(mktemp -d)"; cp -R "$WORK/." "$AVA/"
cat > "$AVA/entities/spouse-li.md" <<'EOF'
---
schema: personal-context/v1
entity: spouse-li
type: person
circle: inner
layer: L3
---
- 称呼：老婆、宝贝；本名 刘凤华
EOF
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$AVA" --view network --audience local --out "$VZ/ava.html"
grep -q '"avatar": "刘"' "$VZ/ava.html" && ok "内嵌本名头像='刘'" || bad "内嵌本名头像未取到刘"
grep -q '"avatar": "老"' "$VZ/ava.html" && bad "头像误回退成'老'" || ok "头像未误回退成老"
rm -rf "$AVA"

# [v12] 群组实体（夫妇/父母）网络节点显中文、绝不外露英文 slug；成员从「## 成员」解析
GRP="$(mktemp -d)"; cp -R "$WORK/." "$GRP/"
cat > "$GRP/entities/friends-liu-wu.md" <<'EOF'
---
schema: personal-context/v1
entity: friends-liu-wu
type: person
circle: close
layer: L2
source: declared
updated: 2026-10-20
---
# 刘铭儇 & 吴雪婷 夫妇
## 成员
- **刘铭儇**（男）：吉利后端。
- **吴雪婷**（女）：设计师。
## 关系
- 老羊撮合的。
EOF
cat > "$GRP/entities/parents-baoji.md" <<'EOF'
---
schema: personal-context/v1
entity: parents-baoji
type: person
circle: inner
layer: L3
source: declared
updated: 2026-10-20
---
# 父母（宝鸡）
## 基本
- 都在宝鸡退休。
EOF
$PY - "$HERE" "$GRP" <<'PY' && ok "群组节点中文显示+slug 不外露" || bad "群组命名回归"
import sys, os, importlib
here, grp = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(here, "scripts"))
viz = importlib.import_module("viz")
payload = viz.build_payload(grp, "local", {"L0","L1","L2","L3"}, False, True, "all")
people = {p["id"]: p for p in payload["people"]}
couple = people["friends-liu-wu"]
assert couple["is_group"] is True, couple
assert couple["members"] == ["刘铭儇", "吴雪婷"], couple["members"]
assert couple["avatar"] == "刘吴", couple["avatar"]
assert "刘" in couple["short"] and "夫妇" in couple["short"], couple["short"]
assert "**" not in couple.get("summary", ""), couple.get("summary")  # 摘要不带裸 markdown
assert not couple["summary"].startswith("刘铭儇"), couple["summary"]  # 摘要不重复成员首条
assert "friends-liu-wu" not in couple["label"] and "friends-liu-wu" not in couple["realname"], couple
assert "（好友）" == couple["identity"], couple["identity"]
parents = people["parents-baoji"]
assert parents["is_group"] is True
assert parents["identity"] == "", parents["identity"]  # 父母第二行不重复括弧
assert "parents-baoji" not in (parents["label"] + parents["short"]), parents
assert parents["short"] == "父母", parents["short"]
# 「**刘铭儇**（男）：…」冒号前加粗是叙事句，必须按文本 {t}（交前端加粗），不能当字段 {k,v} 残留 **
mem_zone = next(z for z in couple["zones"] if z["heading"] == "成员")
assert all("k" not in it and "**" in it.get("t", "") for it in mem_zone["items"]), mem_zone
print("OK group naming")
PY
rm -rf "$GRP"


# [v10.2] P2-2 方向卡锁由实际 locked 驱动：local 有/空内容都不硬编码 🔒；cloud 真锁才显锁
grep -q "想去的地方 🔒" "$VZ/all.html" && bad "方向卡硬编码锁图标" || ok "方向卡 local 不硬编码 🔒"
grep -q "不带出" "$VZ/cloud.html" && ok "cloud 敏感维度显锁块" || bad "cloud 缺锁块"

# [v10.2] P1-2 标准空模板可见文本无 <尖括号占位>/示例标签/说明句
EMPTY3="$(mktemp -d)"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$EMPTY3" --view all --audience local --out "$VZ/empty3.html"
for s in 怎么称呼 可留空 可只给 ENTP 急脾气 选择困难 对齐风格 随时可改; do expect_grep0 "$s" "$VZ/empty3.html"; done
rm -rf "$EMPTY3"


# 真实 headless 点击验收（无 Chrome 环境 SKIP，不 FAIL；本机必须实跑留证）
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ -x "$CHROME" ]; then
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/all.html#person=colleague-wang" > "$VZ/dom_wang.html" 2>/dev/null
  grep -q "王工" "$VZ/dom_wang.html" && grep -q "API 评审" "$VZ/dom_wang.html" \
    && ok "headless #person=colleague-wang 右栏出同事档案(真实点击)" || bad "headless 未渲染同事档案"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/all.html#view=profile" > "$VZ/dom_me.html" 2>/dev/null
  grep -q "张三" "$VZ/dom_me.html" && ok "headless #view=profile 出'我'档案" || bad "headless 未出我档案"
  # [v10.1] 关系网常态只显短中文关系词，年份胶囊仅 hover（渲染 DOM 不出现 ·20xx起）
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/all.html#view=network" > "$VZ/dom_net.html" 2>/dev/null
  grep -q "配偶" "$VZ/dom_net.html" && ok "常态关系词『配偶』在" || bad "缺常态关系词 配偶"
  grep -q "子女" "$VZ/dom_net.html" && ok "常态关系词『子女』在" || bad "缺常态关系词 子女"
  grep -q "同事" "$VZ/dom_net.html" && ok "常态关系词『同事』在" || bad "缺常态关系词 同事"
  grep -q "认识" "$VZ/dom_net.html" && ok "常态关系词『认识』在" || bad "缺常态关系词 认识"
  grep -qE "·20[0-9]{2}起" "$VZ/dom_net.html" && bad "常态常显年份胶囊" || ok "常态不常显年份胶囊(hover 才出)"

  # [v10.1] 圆内显常用称呼"老婆"（非仅单字刘）；本名回退链由上方 JSON avatar='刘' 断言守住
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/ava.html#person=spouse-li" > "$VZ/dom_ava.html" 2>/dev/null
  grep -q '刘凤华' "$VZ/dom_ava.html" && ok "headless 节点保留中文全名" || bad "人物中文全名丢失"
  # [v10.2] P2-3 **加粗** 交前端 md() 渲染成 <strong>，渲染 DOM 无裸 **
  BOLD="$(mktemp -d)"; cp -R "$WORK/." "$BOLD/"
  cat > "$BOLD/profile/work.md" <<'EOF'
---
layer: L1
---
## 一句话定位
做 **AI Agent 工程**，正在落地。
EOF
  expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$BOLD" --view profile --audience local --out "$VZ/bold.html"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/bold.html#view=profile&expand=all" > "$VZ/dom_bold.html" 2>/dev/null
  grep -q "<strong>" "$VZ/dom_bold.html" && ok "headless **加粗** 渲染为 <strong>" || bad "加粗未渲染"
  rm -rf "$BOLD"
  # [v10.2] P2-5 view 三态：network=右栏空 / profile=仅右栏 / all=左右都在
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/all.html#view=network" > "$VZ/dom_vnet.html" 2>/dev/null
  grep -q "view-network" "$VZ/dom_vnet.html" && ok "#view=network 切到网络视图(右栏隐藏,见截图)" || bad "network 视图未接线"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/all.html#view=profile" > "$VZ/dom_vprof.html" 2>/dev/null
  grep -q "view-profile" "$VZ/dom_vprof.html" && ok "#view=profile 切到档案视图" || bad "profile 视图未接线"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/all.html#view=all" > "$VZ/dom_vall.html" 2>/dev/null
  grep -q "view-all" "$VZ/dom_vall.html" && ok "#view=all 默认左右都在" || bad "all 视图缺失"

  # [v10.3] N1 空仓 finance/health 模板指南句不得当已记录条目
  EMPT=$(mktemp -d); "$PY" "$HERE/scripts/init.py" --path "$EMPT" >/dev/null 2>&1
  "$PY" "$HERE/scripts/viz.py" --data "$EMPT" --audience local --out "$VZ/empt.html" >/dev/null 2>&1
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/empt.html#view=profile&expand=all" > "$VZ/dom_empt.html" 2>/dev/null
  for s in 永不记 只记区间 账户号 精确金额 证件号; do
    grep -q "$s" "$VZ/dom_empt.html" && bad "空仓泄漏模板指南句: $s" || true
  done
  ok "空仓 finance/health 无模板指南句(永不记/只记区间/账户号/精确金额/证件号=0)"
  # [v10.3] N2 空仓 relations 注释示例边不产生幽灵提示条
  grep -q "未记录实体" "$VZ/dom_empt.html" && bad "空仓出现幽灵边提示条" || ok "空仓无幽灵边提示条"
  # [v10.3] N3 kv-key/条目加粗渲染为 <strong>，可见文本无裸 **
  grep -q "<strong>" "$VZ/dom_bold.html" && ok "加粗渲染 <strong>(kv-key/条目)" || bad "缺 <strong>"
  # 注：注入 JSON 保留原始 markdown（含 **）属正常，可见 #doc 渲染无裸 ** 由 <strong> 兜底
  # [v10.3] 真幽灵边（指向缺失实体文件）仍 fail-closed 跳过并提示（不被注释清洗吞掉）
  GHT=$(mktemp -d); cp -R "$HERE/examples/." "$GHT/"
  cat >> "$GHT/relations.md" <<'EOF'
- from: missing-ghost
  type: knows
  to: barber-liu
EOF
  "$PY" "$HERE/scripts/viz.py" --data "$GHT" --audience local --out "$VZ/ghost.html" >/dev/null 2>&1
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/ghost.html#view=network" > "$VZ/dom_ghost.html" 2>/dev/null
  grep -q "未记录实体" "$VZ/dom_ghost.html" && ok "真幽灵边仍 fail-closed 提示" || bad "真幽灵边提示丢失"
  rm -rf "$EMPT" "$GHT"
  # [v10.3] 确定性几何坐标断言：三档 GEO_OK（圆不相交/me 间距/胶囊互不相交/离圆≥8/不压中心扇形）
  for v in all network; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
      --dump-dom "file://$VZ/all.html#view=$v" > "$VZ/dom_geo_$v.html" 2>/dev/null
    grep -q "GEO_OK" "$VZ/dom_geo_$v.html" && ok "#view=$v 几何 GEO_OK(圆不相交/胶囊避让/不压中心)" || bad "#view=$v 几何未达标"
  done
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=2000 \
    --dump-dom "file://$VZ/all.html#view=network" > "$VZ/dom_geo390.html" 2>/dev/null
  grep -q "GEO_OK" "$VZ/dom_geo390.html" && ok "390 窄屏几何 GEO_OK(圆不相交/胶囊避让/不裁切)" || bad "390 几何未达标"
  # [v10.4] 节点 chip 方案：取消常驻浮动边胶囊、关系收进节点、长名 6 字截断、390 两档 GEO_OK
  grep -q 'class="edgepill"' "$VZ/dom_net.html" && bad "仍残留常驻浮动边胶囊" || ok "常驻浮动边胶囊已取消(关系收进节点 chip)"
  grep -q 'class="ident"' "$VZ/dom_net.html" && ok "节点第二行身份(本名/称呼+关系括弧)承载关系" || bad "缺身份行关系括弧"
  grep -q '（同事）' "$VZ/dom_net.html" && ok "同事关系括弧在节点" || bad "缺（同事）"
  grep -q "常去的理发店师" "$VZ/dom_net.html" && ok "长节点名 6 字截断 ellipsis" || bad "长名未截断"
  for v in all network; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --run-all-compositor-stages-before-draw --virtual-time-budget=2000 \
      --window-size=390,844 --dump-dom "file://$VZ/all.html#view=$v" > "$VZ/dom_geo390_$v.html" 2>/dev/null
    grep -q "GEO_OK" "$VZ/dom_geo390_$v.html" && ok "390 #view=$v GEO_OK(节点组不相交/不出界/中心净空/legend完整/居中)" || bad "390 #view=$v 几何未达标"
  done
  # [v10.1 收尾] ?netw 确定性窄屏钩子：绕过 headless innerWidth 兜底 500，按真机净宽 346/316 测几何
  for nw in 346 316; do
    for v in all network; do
      "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --run-all-compositor-stages-before-draw --virtual-time-budget=2000 \
        --window-size=390,844 --dump-dom "file://$VZ/all.html?netw=$nw#view=$v" > "$VZ/dom_geo_nw${nw}_$v.html" 2>/dev/null
      grep -q "GEO_OK" "$VZ/dom_geo_nw${nw}_$v.html" && ok "netw=$nw #view=$v GEO_OK(节点组在#net内/南节点不压mehint/中心净空/legend)" || bad "netw=$nw #view=$v 几何未达标"
    done
  done
  # 新网图不再用亲疏圆环冒充多跳层数。保留三种亲疏标记，路径按真实边。
  for term in 核心圈 重要圈 外围圈; do
    grep -q "$term" "$VZ/dom_net.html" && ok "亲疏标记 $term 保留" || bad "缺亲疏标记 $term"
  done
  grep -q 'id="person-search"' "$VZ/dom_net.html" && ok "人物中文检索入口存在" || bad "缺人物检索"
  # 初态按容量折叠，完整称呼不应强制出现在首屏；仍须可从导航/档案数据找回。
grep -q '常去的理发店师傅' "$VZ/dom_net.html" && ok "完整长称呼保留在可搜索记录" || bad "长名丢失"
  # [v10.1] 真实 headless 点击：展开数==有内容数/收起0/点人切换/返回清空/节点两行命名（非仅 hash）
  "$PY" - "$VZ/all.html" "$VZ/click.html" <<'PYEOF'
import sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
inj = """<script>window.addEventListener('load',function(){setTimeout(function(){
var o=[];
var content=document.querySelectorAll('#doc .dimcard:not(.locked)').length;
var ea=document.getElementById('expand-all');
if(ea){ea.click();o.push('EXP='+document.querySelectorAll('#doc .dimcard.sel').length+'/'+content);
document.getElementById('collapse-all').click();o.push('COL='+document.querySelectorAll('#doc .dimcard.sel').length);}
var w=document.querySelector('.node[data-id="spouse-li"]');
if(w){w.click();o.push('PER='+(document.querySelector('#doc h2')?document.querySelector('#doc h2').textContent.trim():'?'));
o.push('CRUMB='+(document.querySelector('#doc .crumb')?document.querySelector('#doc .crumb').textContent:''));}
var b=document.getElementById('back-net');
if(b){b.click();o.push('BACKSEL='+document.querySelectorAll('#net .node.sel').length);}
o.push('NETL='+document.getElementById('net').textContent.includes('李'));
var d=document.createElement('div');d.id='clickout';d.textContent='CLICK||'+o.join(';');document.body.appendChild(d);},500);});</script>"""
src = src.replace("</body>", inj + "</body>")
pathlib.Path(sys.argv[2]).write_text(src, encoding="utf-8")
PYEOF
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=3000 \
    --dump-dom "file://$VZ/click.html" > "$VZ/dom_click.html" 2>/dev/null
  grep -qE 'EXP=[0-9]+/[0-9]+' "$VZ/dom_click.html" && grep -qE 'EXP=([0-9]+)/\1' "$VZ/dom_click.html" \
    && ok "真实点击「全部展开」open 数==有内容卡数" || bad "全部展开 open 数≠有内容数"
  grep -q 'COL=0' "$VZ/dom_click.html" && ok "真实点击「全部收起」open 数==0" || bad "全部收起未清空"
  grep -q 'PER=李' "$VZ/dom_click.html" && ok "真实点击节点右栏切到人物(李)" || bad "点人未切换详情"
  grep -q 'CRUMB=' "$VZ/dom_click.html" && ok "人物页有面包屑" || bad "人物页缺面包屑"
  grep -q 'BACKSEL=0' "$VZ/dom_click.html" && ok "「返回关系网」清空选中态回总览" || bad "返回后选中态未清空"
  grep -q 'NETL=true' "$VZ/dom_click.html" && ok "节点网络可见人物称呼(非仅单字)" || bad "节点名缺失"
  grep -q 'id="back-net"' "$VZ/dom_click.html" && ok "右栏有「返回关系网」入口" || bad "缺返回关系网按钮"
  # [v10.1] 老婆夹具：圆内"老婆"、下方"刘凤华（妻子）"；点人→面包屑"老婆 · 刘凤华"；返回清空
  "$PY" - "$VZ/ava.html" "$VZ/click2.html" <<'PYEOF'
import sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
inj = """<script>window.addEventListener('load',function(){setTimeout(function(){
var o=[];
o.push('FULLNAME='+(document.querySelector('.node[data-id="spouse-li"] .nm')||{}).textContent);
o.push('IDENT='+document.getElementById('net').textContent.includes('（配偶）'));
var d=document.createElement('div');d.id='clickout';d.textContent='CLICK2||'+o.join(';');document.body.appendChild(d);},500);});</script>"""
src = src.replace("</body>", inj + "</body>")
pathlib.Path(sys.argv[2]).write_text(src, encoding="utf-8")
PYEOF
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --virtual-time-budget=3000 \
    --dump-dom "file://$VZ/click2.html" > "$VZ/dom_click2.html" 2>/dev/null
  grep -q 'FULLNAME=刘凤华' "$VZ/dom_click2.html" && ok "配偶节点全名刘凤华可读" || bad "配偶节点未显示全名"
  grep -q 'IDENT=true' "$VZ/dom_click2.html" && ok "未提供性别不猜妻子，配偶中性关系保留" || bad "配偶关系行丢失"
fi

# ============ [v11] 收录宪法 / freshness / --checkup / 过期弱提示（层门禁与 fail-closed 不变） ============
echo "== v11 ① 文档：00 宪法存在且含三问/四去向/不监听/断舍离/provenance；SKILL 与 05 引用 =="
[ -f "$HERE/references/00-constitution.md" ] && ok "00-constitution.md 存在" || bad "缺 00 宪法"
grep -q "收录三问" "$HERE/references/00-constitution.md" && ok "宪法含收录三问" || bad "宪法缺收录三问"
grep -q "四去向" "$HERE/references/00-constitution.md" && ok "宪法含四去向" || bad "宪法缺四去向"
grep -q "不监听" "$HERE/references/00-constitution.md" && ok "宪法写明不监听日常对话" || bad "宪法缺不监听"
grep -q "断舍离" "$HERE/references/00-constitution.md" && ok "宪法含断舍离/时效" || bad "宪法缺断舍离"
grep -q "provenance" "$HERE/references/00-constitution.md" && ok "宪法预留 provenance" || bad "宪法缺 provenance"
grep -q "00-constitution" "$HERE/SKILL.md" && ok "SKILL.md 引用宪法为写入门禁" || bad "SKILL 未引用宪法"
grep -q "00-constitution" "$HERE/references/05-write-protocol.md" && ok "05 写协议引用宪法" || bad "05 未引用宪法"

echo "== v11 ②③④ freshness 夹具：current 超期 WARN 非阻断 / stable 不误报 / checkup 只列不删 / 过期 L3 锁不变 =="
FRESH="$(mktemp -d)"; mkdir -p "$FRESH/profile" "$FRESH/inbox"
cat > "$FRESH/profile/work.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: work
freshness: current
source: declared
updated: 2025-01-01
---
- 最近在忙：旧项目 X
EOF
cat > "$FRESH/ME.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: identity
freshness: stable
source: declared
updated: 2025-01-01
---
# 张三
- 称呼：张三
EOF
cat > "$FRESH/profile/health.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
freshness: current
source: declared
updated: 2025-01-01
---
## 过敏
- 青霉素过敏（敏感明文）
EOF
# v12：本地健康授权门（full），否则 fail-closed 连 local 也不读健康
cat > "$FRESH/CONSENT-health.md" <<'EOF'
---
scope: full
granted: true
granted_date: 2025-01-01
source: user_session
updated: 2025-01-01
---
EOF
cat > "$FRESH/inbox/draft-old.md" <<'EOF'
---
status: draft
date: 2025-01-01
suggest_domain: preferences
---
- 内容：旧候选草稿
EOF

# ② current 超期 → WARN 非阻断 rc0；stable 老身份不被误报（报告写到 /tmp，不污染夹具 hash）
$PY "$HERE/scripts/lint.py" --data "$FRESH" --today 2026-10-20 > /tmp/v11_lint.txt 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "current 超期 lint rc=0(WARN 非阻断)" || bad "current 超期 lint rc=$rc"
grep -q "profile/work.md: 可能过期" /tmp/v11_lint.txt && ok "current 超期出复核提示(WARN 非阻断,rc0)" || bad "缺 current 过期提示"
grep -qE "ME\.md:.*可能过期" /tmp/v11_lint.txt && bad "stable 老 ME 被误报过期" || ok "stable 老身份不误报过期"

# ③ checkup 列超期 current + 旧 inbox；前后 *.md hash 一致（只列不删，报告写 /tmp）
h1=$(find "$FRESH" -name '*.md' -type f -exec md5 -q {} \; | sort | md5 -q)
$PY "$HERE/scripts/lint.py" --data "$FRESH" --checkup --today 2026-10-20 > /tmp/v11_checkup.txt 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "checkup rc=0" || bad "checkup rc=$rc"
h2=$(find "$FRESH" -name '*.md' -type f -exec md5 -q {} \; | sort | md5 -q)
[ "$h1" = "$h2" ] && ok "checkup 只列不删(前后 *.md hash 一致)" || bad "checkup 改动了文件"
grep -q "profile/work.md" /tmp/v11_checkup.txt && ok "checkup 列出超期 current" || bad "checkup 未列超期 current"
grep -q "draft-old.md" /tmp/v11_checkup.txt && ok "checkup 列出旧 inbox 草稿" || bad "checkup 未列旧草稿"

# ④ 过期 L3：gate cloud 仍 rc=2、0 明文，仅中性提示；local rc0
rc=0; out=$($PY "$HERE/scripts/gate.py" --data "$FRESH" --domain health --audience cloud --emit 2>&1) || rc=$?
[ "$rc" -eq 2 ] && ok "过期 L3 cloud 仍 rc=2(层门禁不变)" || bad "过期 L3 cloud rc=$rc"
echo "$out" | grep -q "青霉素" && bad "过期 L3 cloud 泄露明文" || ok "过期 L3 cloud 0 明文"
echo "$out" | grep -q "可能过期" && bad "P2-5 HOLD 被拦场景不应单独打时效行" || ok "P2-5 cloud HOLD(rc=2) 降级时效行避免噪声"
rc=0; out=$($PY "$HERE/scripts/gate.py" --data "$FRESH" --domain health --audience local --emit 2>&1) || rc=$?
[ "$rc" -eq 0 ] && ok "过期 L3 local rc=0 且放行" || bad "过期 L3 local rc=$rc"
echo "$out" | grep -q "可能过期" && ok "local 正常保留过期弱提示" || bad "local 缺过期弱提示"
# viz：cloud 锁明文=0 但显中性提示；local 显过期小注
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$FRESH" --view all --audience cloud --out "$FRESH/c.html"
expect_grep0 "青霉素" "$FRESH/c.html"
grep -q "可能过期" "$FRESH/c.html" && ok "viz cloud 显中性过期提示且不泄明文" || bad "viz cloud 缺过期提示"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$FRESH" --view all --audience local --out "$FRESH/l.html"
grep -q "可能过期" "$FRESH/l.html" && ok "viz local 显过期小注" || bad "viz local 缺过期小注"
rm -rf "$FRESH"

# ============ [v11.1] 红队 P1×2 / P2 修复回归（fail-closed/云锁/几何不回退） ============
echo "== v11.1 ① gate 时效只用文件自身 domain：老 identity 不被 --domain work 误报，过期 work 仍报 =="
F2="$(mktemp -d)"; mkdir -p "$F2/profile"
cat > "$F2/ME.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: identity
source: declared
updated: 2025-01-01
---
# 张三
- 称呼：张三
EOF
cat > "$F2/profile/work.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: work
freshness: current
review_cycle: 15d
source: declared
updated: 2026-10-01
---
- 最近在忙：旧项目
EOF
cat > "$F2/profile/preferences.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: preferences
freshness: stable
source: declared
updated: 2026-10-01
---
- 喜欢先给结论
- 这条是待办：明早检查X
EOF
out=$($PY "$HERE/scripts/gate.py" --data "$F2" --domain work --audience local --emit 2>&1) || true
echo "$out" | grep -q "ME.md：可能过期" && bad "P1-1 老 identity 被 --domain work 误报过期" || ok "P1-1 老 identity 无 freshness 不被误报"
echo "$out" | grep -q "可能过期" && ok "P1-1 过期 work 仍给时效提示" || bad "P1-1 过期 work 未提示"

echo "== v11.1 ② checkup [d] 扫描 stable 分片（过程词误入） =="
$PY "$HERE/scripts/lint.py" --data "$F2" --checkup --today 2026-10-20 > /tmp/v111_checkup.txt 2>&1; rc=$?
grep -q "preferences.md" /tmp/v111_checkup.txt && grep -q "\[d\]" /tmp/v111_checkup.txt && ok "P1-2 stable preferences 过程词进 [d]" || bad "P1-2 未列出 stable 分片过程词"

echo "== v11.1 ③ 自定义 review_cycle=15d 覆盖默认 =="
$PY "$HERE/scripts/lint.py" --data "$F2" --today 2026-10-20 > /tmp/v111_lint.txt 2>&1
grep -q "复核期 15 天" /tmp/v111_lint.txt && ok "P2-2 review_cycle=15d 覆盖默认 60 天" || bad "P2-2 review_cycle 未生效"

echo "== v11.1 ④ A/B 判别式文档统一（相处/沟通方式=A，某类产物=B） =="
grep -q "相处/沟通方式" "$HERE/references/00-constitution.md" && ok "00 含 A/B 判别式（相处/沟通方式）" || bad "00 缺判别式"
grep -q "某一类产物" "$HERE/references/00-constitution.md" && ok "00 含判别式（某一类产物）" || bad "00 缺产物判据"
grep -q "先给结论" "$HERE/references/00-constitution.md" && ok "先给结论统一归 A（沟通方式）" || bad "先给结论未归 A"
grep -q "小标题别玩花样" "$HERE/references/00-constitution.md" && ok "小标题别玩花样归 B（产物规范）" || bad "小标题未归 B"
if grep -q "别绕弯子 / 小标题别玩花样" "$HERE/references/00-constitution.md"; then bad "00 仍有 A/B 矛盾例句"; else ok "00 不再把别绕弯子与产物规范并列"; fi

echo "== v11.1 ⑤ stable 年度回看只读：checkup 前后 *.md hash 不变 =="
h1=$(find "$F2" -name '*.md' -type f -exec md5 -q {} \; | sort | md5 -q)
$PY "$HERE/scripts/lint.py" --data "$F2" --checkup --today 2026-10-20 >/dev/null 2>&1
h2=$(find "$F2" -name '*.md' -type f -exec md5 -q {} \; | sort | md5 -q)
[ "$h1" = "$h2" ] && ok "stable 年度回看只读不改文件" || bad "checkup 改动了文件"
rm -rf "$F2"

# ============ [v12] 健康本地授权门 + 最新/历史/读时diff（fail-closed，与 L3 云门独立） ============
mk_health_fixture() {
  local d="$1" scope="$2" granted="$3"
  mkdir -p "$d/profile"
  cat > "$d/ME.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: identity
source: declared
updated: 2026-10-22
---
# 张三
EOF
  cat > "$d/profile/health.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
source: declared
updated: 2026-10-22
audience: local
---
## 过敏
- 青霉素过敏（敏感明文）
## 最新关键指标
- 指标 ldl_c | 数值 3.6 | 单位 mmol/L | 参考 <3.4 | 日期 2026-10-01 | 机构 甲院 | 方法 酶法 | 采血条件 空腹12h | provenance imported_report
EOF
  if [ -n "$scope" ]; then
    cat > "$d/CONSENT-health.md" <<EOF
---
scope: $scope
granted: $granted
granted_date: 2026-10-01
source: user_session
updated: 2026-10-01
---
EOF
  fi
}

echo "== v12 ① 无 CONSENT：local 也不输出结构化健康（fail-closed），cloud 仍锁，--check-consent 未开启 =="
H1="$(mktemp -d)"; mk_health_fixture "$H1" "" ""
rc=0; out=$($PY "$HERE/scripts/gate.py" --data "$H1" --domain health --audience local --emit 2>&1) || rc=$?
[ "$rc" -eq 0 ] && ok "无授权 gate health local rc=0（中性引导，非错误）" || bad "无授权 local rc=$rc"
echo "$out" | grep -q "青霉素" && bad "无授权 local 泄露健康明文" || ok "无授权 local 0 健康明文"
echo "$out" | grep -q "HEALTH-CONSENT" && ok "无授权出 fail-closed 引导" || bad "缺 HEALTH-CONSENT 引导"
rc=0; out=$($PY "$HERE/scripts/gate.py" --data "$H1" --domain health --audience cloud --emit 2>&1) || rc=$?
echo "$out" | grep -q "青霉素" && bad "无授权 cloud 泄露健康明文" || ok "无授权 cloud 0 明文"
$PY "$HERE/scripts/gate.py" --data "$H1" --check-consent 2>&1 | grep -q "未开启" && ok "--check-consent 报未开启" || bad "--check-consent 未报未开启"

echo "== v12 ② index_only 不出指标/解读；facts_only 只给事实不给趋势计数 =="
H2="$(mktemp -d)"; mk_health_fixture "$H2" "index_only" "true"
out=$($PY "$HERE/scripts/gate.py" --data "$H2" --domain health --audience local --emit 2>&1)
echo "$out" | grep -q "index_only" && ok "index_only 提示仅原件索引" || bad "缺 index_only 提示"
echo "$out" | grep -q "青霉素" && bad "index_only 仍出健康明文" || ok "index_only 0 明文"
H3="$(mktemp -d)"; mk_health_fixture "$H3" "facts_only" "true"
out=$($PY "$HERE/scripts/gate.py" --data "$H3" --domain health --audience local --emit 2>&1)
echo "$out" | grep -q "facts_only" && ok "facts_only 降级提示（不给趋势/计数）" || bad "缺 facts_only 提示"
echo "$out" | grep -q "青霉素" && ok "facts_only 保留事实（过敏）" || bad "facts_only 丢了事实"

echo "== v12 ③ 撤回 granted=false：降级且历史/文件不被删 =="
H4="$(mktemp -d)"; mk_health_fixture "$H4" "off" "false"
before=$(md5 -q "$H4/profile/health.md")
out=$($PY "$HERE/scripts/gate.py" --data "$H4" --domain health --audience local --emit 2>&1)
after=$(md5 -q "$H4/profile/health.md")
[ "$before" = "$after" ] && ok "撤回不删除/不改写历史健康文件" || bad "撤回改动了健康文件"
echo "$out" | grep -q "青霉素" && bad "撤回后仍出明文" || ok "撤回后 0 明文"
$PY "$HERE/scripts/gate.py" --data "$H4" --check-consent 2>&1 | grep -q "撤回/未授权" && ok "--check-consent 报撤回" || bad "撤回状态未报"

echo "== v12 ④ 读时趋势：同院同法 improved/worsened、跨院 fluctuating、练后 CK 不标 worsened =="
$PY - "$HERE" <<'PY' && ok "趋势标签：同院同法方向/跨院参考/练后CK中性/new" || bad "趋势标签派生错误"
import sys; sys.path.insert(0, sys.argv[1] + "/scripts")
import mectx_common as C
def row(name,v,lab,method,cond=""):
    return {"name":name,"value":v,"lab":lab,"method":method,"preconditions":cond}
assert C.trend_label(row("ldl_c",3.6,"甲院","酶法"), row("ldl_c",2.8,"甲院","酶法"))=="improved"
assert C.trend_label(row("ldl_c",2.8,"甲院","酶法"), row("ldl_c",3.9,"甲院","酶法"))=="worsened"
assert C.trend_label(row("ldl_c",3.6,"甲院","酶法"), row("ldl_c",4.2,"乙院","比色"))=="fluctuating"
assert C.trend_label(row("ck",300,"甲院","酶偶联","静息"), row("ck",900,"甲院","酶偶联","练后高强度"))=="fluctuating"
assert C.trend_label(None, row("ua",480,"甲院","尿酸酶"))=="new"
PY

echo "== v12 ⑤ 历史快照 append-only：health_sections 解析最新/历史，快照只增不覆盖（人工追加计数） =="
H5="$(mktemp -d)"; mk_health_fixture "$H5" "full" "true"
cat >> "$H5/profile/health.md" <<'EOF'
## 历史快照（append-only）
- 指标 ldl_c | 数值 3.6 | 单位 mmol/L | 参考 <3.4 | 日期 2025-10-01 | 机构 甲院 | 方法 酶法 | 采血条件 空腹 | provenance imported_report
EOF
$PY - "$HERE" "$H5" <<'PY' && ok "health_sections 解析最新1条+历史1条（append-only 不覆盖）" || bad "health_sections 解析失败"
import sys; sys.path.insert(0, sys.argv[1]+"/scripts")
import mectx_common as C
meta, body = C.parse_frontmatter(open(sys.argv[2]+"/profile/health.md", encoding="utf-8").read())
latest, hist = C.health_sections(body)
assert len(latest)==1 and len(hist)==1, (len(latest), len(hist))
PY

echo "== v12 ⑥ 缺 CONSENT 时 lint 给非阻断 WARN（rc0，不阻断非健康） =="
$PY "$HERE/scripts/lint.py" --data "$H1" > /tmp/v12_lint.txt 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "缺授权 lint rc=0（WARN 非阻断）" || bad "缺授权 lint rc=$rc"
grep -q "CONSENT-health.md" /tmp/v12_lint.txt && ok "lint 出如何开启授权引导" || bad "缺授权引导 WARN"

echo "== v12 ⑦ 坏头/无授权不崩：健康坏头 fail-closed，gate 非 0 且不抛 =="
H6="$(mktemp -d)"; mkdir -p "$H6/profile"
printf '%s\n' '---' 'bad head' > "$H6/profile/health.md"
rc=0; $PY "$HERE/scripts/gate.py" --data "$H6" --domain health --audience local --emit >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "坏头健康 fail-closed（非0）" || bad "坏头未被拦 rc=0"

echo "== v12 ⑧ P1-1 facts_only 真裁剪：gate local 只见安全事实，指标/结论/里程碑/索引=0；cloud 未confirm 仍 HOLD rc2/0明文 =="
HF="$(mktemp -d)"; mkdir -p "$HF/profile"
cat > "$HF/ME.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: identity
source: declared
updated: 2026-10-22
---
# 张三
EOF
cat > "$HF/profile/health.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
source: declared
updated: 2026-10-22
audience: local
---
## 过敏
- 青霉素过敏（安全事实）
## 在服药
- 无
## 最新关键指标
- 指标 ldl_c | 数值 3.62 | 单位 mmol/L | 参考 <3.4 | 日期 2026-10-01 | 机构 甲院 | 方法 酶法 | 采血条件 空腹 | provenance imported_report
## 结论区
- 总检结论 CONCL：血脂较去年回落，建议继续饮食控制
## 变化里程碑
- 脂肪肝健身后持续好转（本人确认）
## 原件索引
- private/health/2025_checkup.pdf
EOF
cat > "$HF/CONSENT-health.md" <<'EOF'
---
scope: facts_only
granted: true
granted_date: 2026-10-01
source: user_session
updated: 2026-10-01
---
EOF
out=$($PY "$HERE/scripts/gate.py" --data "$HF" --domain health --audience local --emit 2>&1)
echo "$out" | grep -q "青霉素" && ok "facts_only gate local 保留过敏事实" || bad "facts_only 丢了过敏"
echo "$out" | grep -q "3.62" && bad "facts_only gate 泄露指标值3.62" || ok "facts_only gate 0 指标值"
echo "$out" | grep -q "CONCL" && bad "facts_only gate 泄露结论" || ok "facts_only gate 0 结论"
echo "$out" | grep -q "脂肪肝" && bad "facts_only gate 泄露里程碑" || ok "facts_only gate 0 里程碑"
echo "$out" | grep -q "2025_checkup.pdf" && bad "facts_only gate 泄露原件索引" || ok "facts_only gate 0 索引"
rc=0; $PY "$HERE/scripts/gate.py" --data "$HF" --domain health --audience cloud --emit >/tmp/v12_fo_cloud.txt 2>&1 || rc=$?
[ "$rc" -eq 2 ] && ok "facts_only+cloud 未 confirm 仍 HOLD rc2" || bad "facts_only cloud rc=$rc（应2）"
grep -q "青霉素" /tmp/v12_fo_cloud.txt && bad "facts_only cloud 未confirm 泄露明文" || ok "facts_only cloud 0 明文"
# viz facts_only：只注入安全事实小节，0 指标/历史/里程碑/索引
FDIR=$(mktemp -d)
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$HF" --view profile --audience local --out "$FDIR/fo.html"
grep -q "青霉素" "$FDIR/fo.html" && ok "viz facts_only 注入过敏事实" || bad "viz facts_only 丢过敏"
# 只查真正注入的档案 JSON；页面样式/坐标包含相似数字不能算健康泄露。
$PY - "$FDIR/fo.html" <<'PY' && ok "viz facts_only 0 指标" || bad "viz facts_only 泄露指标值"
import json, re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
payload = json.loads(re.search(r'<script type="application/json" id="mc-data">(.*?)</script>', text, re.S).group(1))
assert "3.62" not in json.dumps(payload, ensure_ascii=False)
PY
grep -q "脂肪肝" "$FDIR/fo.html" && bad "viz facts_only 泄露里程碑" || ok "viz facts_only 0 里程碑"
grep -q "2025_checkup.pdf" "$FDIR/fo.html" && bad "viz facts_only 泄露索引" || ok "viz facts_only 0 索引"

echo "== v12 ⑨ P1-2/P1-3/P2-2/P2-3 趋势：换单位=fluctuating；运动守卫扩 ALT/AST/肌酐/UA；静息真升高仍 worsened；resolved；不可信不驱动 =="
$PY - "$HERE" <<'PY' && ok "趋势：单位不同/运动守卫/静息方向/resolved/置信度 全符合" || bad "趋势派生错误"
import sys; sys.path.insert(0, sys.argv[1] + "/scripts")
import mectx_common as C
def row(name,v,unit,lab,method,cond="",conf="",ref=""):
    return {"name":name,"value":v,"unit":unit,"lab":lab,"method":method,
            "preconditions":cond,"confidence":conf,"ref":ref}
# 换单位但归一后近等（486μmol/L≈8.2mg/dL）→ 仍不强行给方向
assert C.trend_label(row("ua",486,"μmol/L","甲院","尿酸酶"), row("ua",8.2,"mg/dL","甲院","尿酸酶"))=="fluctuating"
# 单位/项目无法归一（hba1c 不同口径、不可换算）→ 不可比，不判方向
assert C.trend_label(row("hba1c",6.1,"%","甲院","高效液相"), row("hba1c",5.9,"mmol/mol","乙院","离子交换"))=="fluctuating"
# P1-3 运动守卫扩到 ALT/AST/肌酐/UA（练后/高强度/脱水升高→fluctuating）
assert C.trend_label(row("alt",30,"U/L","甲院","酶法","静息"), row("alt",80,"U/L","甲院","酶法","练后"))=="fluctuating"
assert C.trend_label(row("ast",25,"U/L","甲院","酶法","静息"), row("ast",95,"U/L","甲院","酶法","训练后"))=="fluctuating"
assert C.trend_label(row("creatinine",70,"μmol/L","甲院","酶法","静息"), row("creatinine",115,"μmol/L","甲院","酶法","脱水"))=="fluctuating"
assert C.trend_label(row("ua",360,"μmol/L","甲院","尿酸酶","静息"), row("ua",480,"μmol/L","甲院","尿酸酶","高强度后"))=="fluctuating"
# 两点都静息、ALT 真持续升高 → 仍 worsened（不一竿子全挡）
assert C.trend_label(row("alt",30,"U/L","甲院","酶法","静息"), row("alt",80,"U/L","甲院","酶法","静息"))=="worsened"
# CK 旧例不回退
assert C.trend_label(row("ck",300,"U/L","甲院","酶偶联","静息"), row("ck",900,"U/L","甲院","酶偶联","练后高强度"))=="fluctuating"
# P2-2 resolved：既往区间外、本次回区间内
assert C.trend_label(row("ldl_c",3.6,"mmol/L","甲院","酶法",ref="<3.4"), row("ldl_c",2.8,"mmol/L","甲院","酶法",ref="<3.4"))=="resolved"
# P2-3 confidence single_measurement/inferred 不驱动方向
assert C.trend_label(row("ldl_c",2.8,"mmol/L","甲院","酶法",conf="confirmed"),
                     row("ldl_c",3.9,"mmol/L","甲院","酶法",conf="single_measurement"))=="fluctuating"
assert C.trend_label(row("ldl_c",2.8,"mmol/L","甲院","酶法",conf="confirmed"),
                     row("ldl_c",3.9,"mmol/L","甲院","酶法",conf="inferred"))=="fluctuating"
# 两点都可信才落方向
assert C.trend_label(row("ldl_c",2.8,"mmol/L","甲院","酶法",conf="confirmed"),
                     row("ldl_c",3.9,"mmol/L","甲院","酶法",conf="confirmed"))=="worsened"
PY

echo "== v14 ① 三级置信趋势：high 同院同法 / mid 跨院单位归一软方向 / none 不可比·单次·运动守卫 =="
$PY - "$HERE" <<'PY' && ok "三级置信：high方向/mid软方向仅供参考/none不可比" || bad "三级置信派生错误"
import sys; sys.path.insert(0, sys.argv[1] + "/scripts")
import mectx_common as C
def row(name,v,unit,lab,method,cond="",conf="",ref=""):
    return {"name":name,"value":v,"unit":unit,"lab":lab,"method":method,
            "preconditions":cond,"confidence":conf,"ref":ref}
# high：同院同法同单位 → 出方向，conf=high
p=row("ldl_c",3.6,"mmol/L","甲院","酶法",conf="confirmed"); c=row("ldl_c",2.8,"mmol/L","甲院","酶法",conf="confirmed")
assert C.trend_label(p,c)=="improved" and C.trend_confidence(p,c)=="high"
# mid：跨院、单位可归一（尿酸 420μmol/L→6.0mg/dL≈357）→ 软方向 improved，conf=mid，不给强箭头
p=row("ua",420,"μmol/L","甲院","尿酸酶",conf="imported_report"); c=row("ua",6.0,"mg/dL","乙院","尿酸酶",conf="imported_report")
assert C.trend_label(p,c)=="improved" and C.trend_confidence(p,c)=="mid"
# mid：血糖跨院同单位但不同机构 → 归一可比，软方向
p=row("fpg",7.2,"mmol/L","甲院","己糖激酶",conf="imported_report"); c=row("fpg",5.8,"mmol/L","乙院","葡萄糖氧化酶",conf="imported_report")
assert C.trend_label(p,c)=="improved" and C.trend_confidence(p,c)=="mid"
# none：单位无法归一（hba1c %↔mmol/mol）→ 不判方向
p=row("hba1c",6.1,"%","甲院","高效液相",conf="imported_report"); c=row("hba1c",5.9,"mmol/mol","乙院","离子交换",conf="imported_report")
assert C.trend_label(p,c)=="fluctuating" and C.trend_confidence(p,c)=="none"
# none：不可信点 single_measurement 不驱动 mid/high
p=row("ua",420,"μmol/L","甲院","尿酸酶",conf="imported_report"); c=row("ua",6.0,"mg/dL","乙院","尿酸酶",conf="single_measurement")
assert C.trend_confidence(p,c)=="none"
# none：运动守卫练后升高不判 worsened（任何档）
p=row("ua",360,"μmol/L","甲院","尿酸酶","静息",conf="imported_report"); c=row("ua",480,"μmol/L","甲院","尿酸酶","高强度后",conf="imported_report")
assert C.trend_label(p,c)=="fluctuating" and C.trend_confidence(p,c)=="none"

# P1-A：跨院、同方法、单位本来就相同（mmol/L，无需换算表）→ 中置信软方向，不判 none
p=row("ldl_c",3.6,"mmol/L","甲院","酶法",conf="confirmed"); c=row("ldl_c",2.8,"mmol/L","乙院","酶法",conf="confirmed")
assert C.trend_label(p,c)=="improved" and C.trend_confidence(p,c)=="mid"
# P1-B：HDL（LOW_BAD，高=好）跨院 mg/dL↔mmol/L 两向方向不能反
p=row("hdl_c",1.0,"mmol/L","甲院","酶法",conf="confirmed"); c=row("hdl_c",55,"mg/dL","乙院","酶法",conf="confirmed")
assert C.trend_label(p,c)=="improved" and C.trend_confidence(p,c)=="mid"  # 55mg≈1.42 升高=好
p=row("hdl_c",1.4,"mmol/L","甲院","酶法",conf="confirmed"); c=row("hdl_c",30,"mg/dL","乙院","酶法",conf="confirmed")
assert C.trend_label(p,c)=="worsened" and C.trend_confidence(p,c)=="mid"  # 30mg≈0.78 降低=差
# TC / TG 跨院换算方向正确（近似系数 ÷38.67 / ÷88.57）
p=row("tc",220,"mg/dL","甲院","酶法",conf="confirmed"); c=row("tc",5.2,"mmol/L","乙院","酶法",conf="confirmed")
assert C.trend_label(p,c)=="improved" and C.trend_confidence(p,c)=="mid"
p=row("tg",180,"mg/dL","甲院","酶法",conf="confirmed"); c=row("tg",1.2,"mmol/L","乙院","酶法",conf="confirmed")
assert C.trend_label(p,c)=="improved" and C.trend_confidence(p,c)=="mid"
# P1-C：运动守卫在归一后判断——肌酐 90μmol/L 安静→1.2mg/dL(≈106)练后，跨单位也必须 none
p=row("creatinine",90,"μmol/L","甲院","酶法","静息",conf="confirmed"); c=row("creatinine",1.2,"mg/dL","乙院","酶法","高强度后",conf="confirmed")
assert C.trend_label(p,c)=="fluctuating" and C.trend_confidence(p,c)=="none"
# P1-C 对照：同为跨单位，但两次都静息、归一后真升高 → 仍可判 mid，不误挡
p=row("creatinine",90,"μmol/L","甲院","酶法","静息",conf="confirmed"); c=row("creatinine",1.2,"mg/dL","乙院","酶法","静息",conf="confirmed")
assert C.trend_label(p,c)=="worsened" and C.trend_confidence(p,c)=="mid"
# 方法明显不同（酶法 vs 比色）即使同单位跨院也不可比 → none
p=row("ldl_c",3.6,"mmol/L","甲院","酶法",conf="confirmed"); c=row("ldl_c",2.8,"mmol/L","乙院","比色",conf="confirmed")
assert C.trend_confidence(p,c)=="none"
PY

echo "== v14 ④ 授权轻量化：style 只改怎么说不改访问；parse_consent 读 style，未授权仍 fail-closed =="
$PY - "$HERE" <<'PY' && ok "style 字段解析且不影响 allowed" || bad "style 解析错误"
import sys,os,tempfile; sys.path.insert(0, sys.argv[1]+"/scripts")
import mectx_common as C
d=tempfile.mkdtemp()
open(os.path.join(d,"CONSENT-health.md"),"w",encoding="utf-8").write(
 "---\nscope: full\ngranted: true\ngranted_date: 2026-10-01\nsource: user_session\nupdated: 2026-10-01\nstyle: gentle\n---\n")
cc=C.parse_consent(d)
assert cc["allowed"] is True and cc["scope"]=="full" and cc["style"]=="gentle"
# 非法 style 值回落 None，不影响授权
open(os.path.join(d,"CONSENT-health.md"),"w",encoding="utf-8").write(
 "---\nscope: full\ngranted: true\ngranted_date: 2026-10-01\nsource: user_session\nupdated: 2026-10-01\nstyle: weird\n---\n")
assert C.parse_consent(d)["style"] is None
# 无文件 → off fail-closed，style None
d2=tempfile.mkdtemp(); cc2=C.parse_consent(d2)
assert cc2["allowed"] is False and cc2["scope"]=="off" and cc2["style"] is None
PY

echo "== v14 ⑤ watchlist 关注因子：auto 仅由既往触发 / 正常人空 / proposed 未确认不生效 / 删除不重加 / finance 不越界 / 三档 =="
$PY - "$HERE" <<'PY' && ok "watchlist auto/proposed/删除/不越界/三档" || bad "watchlist 逻辑错误"
import sys; sys.path.insert(0, sys.argv[1]+"/scripts")
import mectx_common as C
# 1) 痛风既往 → auto 关联 ua(已 stated) 与 creatinine
gout="## 慢病禁忌\n- 痛风史，在服非布司他\n## 关注因子（watchlist）\n- 尿酸 ua | 来源 stated | 原因 痛风史继续盯\n"
wl={w["analyte"]:w["source"] for w in C.derive_watchlist(gout,"")}
assert "ua" in wl and "creatinine" in wl, wl
# 2) 无任何既往史的正常人 → watchlist 为空（除显式目标），不得被塞病名
normal="## 过敏\n- 无\n## 慢病禁忌\n- 无\n"
assert C.derive_watchlist(normal,"")==[], C.derive_watchlist(normal,"")
# 3) proposed 未确认不生效；删除项不被 auto 重加
p="## 关注因子（watchlist）\n- 血压 systolic | 来源 proposed | 原因 建议关注\n- ~~ldl_c~~ | 来源 auto | 原因 删除\n## 慢病禁忌\n- 血脂异常，ldl高\n"
wl3={w["analyte"]:w["source"] for w in C.derive_watchlist(p,"")}
assert "systolic" not in wl3, wl3          # proposed 未确认
assert "ldl_c" not in wl3, wl3             # 删除后不自动重加
# 4) 纯财务文本不派生任何关注项（不越界）
fin="## 财务\n- 现金流月结余2万，股票持仓30万，基金定投"
assert C.derive_watchlist(fin,"")==[]
# 5) body 显式目标 stated（备赛/健身/备孕），非病名
wl5=C.derive_watchlist("", "备赛期想重点盯训练状态")
assert any(w["item"]=="备赛" and w["source"]=="stated" for w in wl5), wl5
# 6) 三档分类：异常固定 / 关注正常也留 / 其余正常折叠
rows=[
 {"name":"ldl_c","status":"偏高"},
 {"name":"ua","status":"正常"},
 {"name":"hdl_c","status":"正常"},
]
fixed,watched,rest=C.watch_tier(rows, {"ua"})
assert [r["name"] for r in fixed]==["ldl_c"]
assert [r["name"] for r in watched]==["ua"]
assert [r["name"] for r in rest]==["hdl_c"]
# 7) 派生结果里绝不出现 finance 关键词（构建只扫健康/目标文本）
for w in C.derive_watchlist(gout,""):
    assert "财务" not in str(w) and "股票" not in str(w)
PY

echo "== v15 ① watchlist 不给正常人硬安病：否认/未见/亲属/家族史/结论原文/模板占位/proposed 原因均不触发 auto =="
$PY - "$HERE" <<'PY' && ok "watchlist 防硬安病：否认/未见/亲属/家族/结论/占位/proposed 原因不触发" || bad "watchlist 仍会给正常人硬安病"
import sys; sys.path.insert(0, sys.argv[1]+"/scripts")
import mectx_common as C
def wl(b, g=""): return [w["analyte"] or w["item"] for w in C.derive_watchlist(b, g)]
assert wl("## 既往史\n- 否认高血压、糖尿病、痛风\n")==[], "否认句被当病史"
assert wl("## 既往史\n- 父亲有高血压，母亲糖尿病\n")==[], "亲属病史被当本人"
assert wl("## 家族史\n- 外公脂肪肝\n")==[], "家族史小节被当本人"
assert wl("## 结论区\n- 腹部B超：未见脂肪肝\n")==[], "结论原文'未见'被当病史"
assert wl("## 关注因子（watchlist）\n- 尿酸 ua | 来源 proposed | 原因 担心痛风\n")==[], "proposed 原因绕过确认"
tpl=open(sys.argv[1]+"/templates/profile/health.md",encoding="utf-8").read()
btpl=open(sys.argv[1]+"/templates/profile/body.md",encoding="utf-8").read()
assert wl(tpl, btpl)==[], ("空白模板示例行被当条目", wl(tpl, btpl))
# 对照：本人正向事实仍正常关联（不能因防误判而失效）
assert set(wl("## 过敏 / 在服药 / 慢病禁忌\n- 慢病：轻度脂肪肝\n"))=={"alt","ldl_c","waist"}
assert set(wl("## 既往史\n- 2023 年确诊痛风，在服非布司他\n"))=={"ua","creatinine"}
assert "健身" in wl("", "## 作息与运动\n- 运动习惯：规律健身，每周4练\n")
PY

echo "== v15 ② 跨院方法空白：通用标准化项走 mid 软方向；非标准化项/方法写明冲突仍 none；resolved 置信随可比性 =="
$PY - "$HERE" <<'PY' && ok "跨院方法空白：标准化项 mid / 非标准化 none / resolved 随可比性" || bad "跨院方法空白判定错误"
import sys; sys.path.insert(0, sys.argv[1]+"/scripts")
import mectx_common as C
def row(n,v,u,lab,method="",cond="空腹",conf="imported_report",ref=""):
    return {"name":n,"value":v,"unit":u,"lab":lab,"method":method,"preconditions":cond,"confidence":conf,"ref":ref}
def tc(p,c): return (C.trend_label(p,c), C.trend_confidence(p,c))
assert tc(row("ua",520,"μmol/L","甲"), row("ua",430,"μmol/L","乙"))==("improved","mid")
assert tc(row("systolic",145,"mmHg","甲"), row("systolic",125,"mmHg","乙"))==("improved","mid")
assert tc(row("ua",8.5,"mg/dL","甲"), row("ua",430,"μmol/L","乙"))==("improved","mid")
assert tc(row("hba1c",6.3,"%","甲"), row("hba1c",5.8,"%","乙"))==("fluctuating","none")
assert tc(row("ck",400,"U/L","甲"), row("ck",200,"U/L","乙"))==("fluctuating","none")
assert tc(row("ldl_c",3.6,"mmol/L","甲","酶法"), row("ldl_c",2.8,"mmol/L","乙","比色"))==("fluctuating","none")
assert tc(row("ua",400,"μmol/L","甲"), row("ua",480,"μmol/L","乙",cond="练后"))==("fluctuating","none")
assert tc(row("ua",520,"μmol/L","甲"), row("ua",430,"μmol/L","乙",conf="single_measurement"))==("fluctuating","none")
assert tc(row("ua",480,"μmol/L","甲","尿酸酶",ref="<420"), row("ua",400,"μmol/L","甲","尿酸酶",ref="<420"))==("resolved","high")
assert tc(row("ua",480,"μmol/L","甲",ref="<420"), row("ua",400,"μmol/L","乙",ref="<416"))==("resolved","mid")
assert tc(row("ldl_c",3.6,"mmol/L","甲","酶法",ref="<3.4"), row("ldl_c",2.8,"mmol/L","乙","比色",ref="<3.4"))==("fluctuating","none")
PY

echo "== v15 ③ 多年历史：比较基准取最近一次（按日期，非文本顺序）；行缺日期继承 ### 小节日期；viz 历点显示全部年份 =="
$PY - "$HERE" <<'PY' && ok "多年历史：基准=最近一次、继承小节日期、历点全量" || bad "多年历史基准错误"
import sys; sys.path.insert(0, sys.argv[1]+"/scripts")
import mectx_common as C
body = """## 最新关键指标
- 指标 ua | 数值 430 | 单位 μmol/L | 参考 <420 | 日期 2026-09-01 | 机构 乙 | 方法  | 采血条件 空腹 | provenance imported_report
## 历史快照
### 2024-09-01 甲院
- 指标 ua | 数值 560 | 单位 μmol/L | 参考 <420 | 机构 甲 | 方法  | 采血条件 空腹 | provenance imported_report
### 2025-09-01 甲院
- 指标 ua | 数值 470 | 单位 μmol/L | 参考 <420 | 机构 甲 | 方法  | 采血条件 空腹 | provenance imported_report
"""
latest, hist = C.health_sections(body)
hby = C.history_by_analyte(hist)
assert [r["date"] for r in hby["ua"]]==["2025-09-01","2024-09-01"], hby["ua"]
prev = hby["ua"][0]
assert prev["value"]==470.0
# 基准=最近一次 2025（甲院）对最新 2026（乙院）：跨院但同单位标准化项 → mid 软方向（不是 high，也不是不比）
assert C.trend_label(prev, latest[0])=="improved" and C.trend_confidence(prev, latest[0])=="mid"
PY
VD="$(mktemp -d)"; mkdir -p "$VD/profile"
cat > "$VD/CONSENT-health.md" <<'MD'
---
schema: personal-context/v1
scope: full
granted: true
granted_date: 2026-10-22
source: user_session
updated: 2026-10-22
---
MD
cat > "$VD/profile/health.md" <<'MD'
---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
confidence: high
source: declared
updated: 2026-10-22
audience: local
---
## 过敏 / 在服药 / 慢病禁忌
- 慢病：痛风（虚构）
## 最新关键指标
- 指标 ua | 数值 400 | 单位 μmol/L | 参考 <420 | 日期 2026-09-01 | 机构 乙 | 方法  | 采血条件 空腹 | provenance imported_report
## 历史快照
### 2024-09-01 甲院
- 指标 ua | 数值 560 | 单位 μmol/L | 参考 <420 | 机构 甲 | 方法  | 采血条件 空腹 | provenance imported_report
### 2025-09-01 甲院
- 指标 ua | 数值 470 | 单位 μmol/L | 参考 <420 | 机构 甲 | 方法  | 采血条件 空腹 | provenance imported_report
MD
$PY "$HERE/scripts/viz.py" --data "$VD" --view profile --audience local --out "$VD/v.html" >/dev/null 2>&1
grep -q "2024-09-01" "$VD/v.html" && grep -q "2025-09-01" "$VD/v.html" && ok "viz 历点显示多年（2024+2025）" || bad "viz 历点仍只显示一年"
grep -q "大致回到正常" "$VD/v.html" && ok "viz mid 档 resolved 有人话文案（不留空）" || bad "viz mid 档 resolved 文案缺失"
rm -rf "$VD"

echo "== v12 ⑩ P2-1 export 按 consent 裁剪：off 不含健康正文；facts_only 只导安全事实 =="
HO="$(mktemp -d)"; mkdir -p "$HO/profile"
cp "$HF/ME.md" "$HO/ME.md"
cp "$HF/profile/health.md" "$HO/profile/health.md"
cat > "$HO/CONSENT-health.md" <<'EOF'
---
scope: off
granted: false
granted_date: 2026-10-01
source: user_session
updated: 2026-10-01
---
EOF
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HO" --all-layers --out "$FDIR/exp_off.md"
grep -q "未导出结构化健康正文" "$FDIR/exp_off.md" && ok "export off 出未授权说明" || bad "export off 缺说明"
grep -q "3.62" "$FDIR/exp_off.md" && bad "export off 泄露指标值" || ok "export off 0 指标正文"
cp "$HF/CONSENT-health.md" "$HO/CONSENT-health.md"
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HO" --all-layers --out "$FDIR/exp_fo.md"
grep -q "青霉素" "$FDIR/exp_fo.md" && ok "export facts_only 导过敏事实" || bad "export facts_only 丢过敏"
grep -q "3.62" "$FDIR/exp_fo.md" && bad "export facts_only 泄露指标值" || ok "export facts_only 0 指标"
grep -q "脂肪肝" "$FDIR/exp_fo.md" && bad "export facts_only 泄露里程碑" || ok "export facts_only 0 里程碑"

echo "== v12 ⑪ 统一 consent 裁剪：export md+zip、gate 换 domain，覆盖 entities 健康分区/network 夹带句；viz 表格；08 协议；390 横滑 =="
HX="$(mktemp -d)"; mkdir -p "$HX/profile" "$HX/entities"
cat > "$HX/ME.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: identity
source: declared
updated: 2026-10-22
---
# 张三
EOF
cat > "$HX/profile/health.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
source: declared
updated: 2026-10-22
audience: local
---
## 过敏
- 青霉素过敏（敏感明文）
## 最新关键指标
- 指标 ldl_c | 数值 2.8 | 单位 mmol/L | 参考 <3.4 | 日期 2026-10-01 | 机构 甲院 | 方法 酶法 | 采血条件 空腹12h | provenance imported_report | confidence confirmed
EOF
cat > "$HX/entities/spouse.md" <<'EOF'
---
schema: personal-context/v1
entity: spouse
type: person
layer: L2
domain: family
source: declared
circle: close
updated: 2026-10-22
---
## 基本
- 称呼：配偶
## 身体情况
- 在备孕（家庭共同计划，敏感）
EOF
cat > "$HX/network.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: network
layer: L2
domain: network
source: declared
updated: 2026-10-22
---
## 核心圈
- spouse 配偶；最该记住：青霉素过敏
EOF
# off：无授权 CONSENT
cat > "$HX/CONSENT-health.md" <<'EOF'
---
scope: off
granted: false
granted_date: 2026-10-01
source: user_session
updated: 2026-10-01
---
EOF
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HX" --all-layers --out "$FDIR/x_off.md"
expect_grep0 "青霉素" "$FDIR/x_off.md"
expect_grep0 "2.8" "$FDIR/x_off.md"
expect_grep0 "备孕" "$FDIR/x_off.md"
grep -q "未导出" "$FDIR/x_off.md" && ok "export off md 出占位说明" || bad "export off md 缺占位"
# zip off（--all-layers 放开层也按 scope 裁剪）
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HX" --format zip --all-layers --out "$FDIR/x_off.zip"
( cd "$FDIR" && unzip -p x_off.zip profile/health.md 2>/dev/null | grep -q "2.8" ) && bad "zip off 泄露 health 指标" || ok "zip off health 0 指标"
( cd "$FDIR" && unzip -p x_off.zip entities/spouse.md 2>/dev/null | grep -q "备孕" ) && bad "zip off 泄露 entities 备孕" || ok "zip off entities 0 备孕"
( cd "$FDIR" && unzip -p x_off.zip network.md 2>/dev/null | grep -q "青霉素" ) && bad "zip off 泄露 network 过敏句" || ok "zip off network 0 过敏"
# gate 换 domain（network/family）local 无授权：entities 健康分区/夹带句被挡
out=$($PY "$HERE/scripts/gate.py" --data "$HX" --entity spouse --domain family --audience local --emit 2>&1) || true
echo "$out" | grep -q "备孕" && bad "gate family local off 泄露备孕" || ok "gate family local off 0 备孕"
out=$($PY "$HERE/scripts/gate.py" --data "$HX" --domain network --audience local --emit 2>&1) || true
echo "$out" | grep -q "青霉素" && bad "gate network local off 泄露过敏句" || ok "gate network local off 0 过敏句"
# facts_only export：过敏安全事实=1，指标/备孕=0
cat > "$HX/CONSENT-health.md" <<'EOF'
---
scope: facts_only
granted: true
granted_date: 2026-10-01
source: user_session
updated: 2026-10-01
---
EOF
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HX" --all-layers --out "$FDIR/x_fo.md"
grep -q "青霉素" "$FDIR/x_fo.md" && ok "export facts_only 保留过敏" || bad "export facts_only 丢过敏"
expect_grep0 "2.8" "$FDIR/x_fo.md"
expect_grep0 "备孕" "$FDIR/x_fo.md"
# full 回归：export/gate 完整可见
cat > "$HX/CONSENT-health.md" <<'EOF'
---
scope: full
granted: true
granted_date: 2026-10-01
source: user_session
updated: 2026-10-01
---
EOF
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HX" --all-layers --out "$FDIR/x_full.md"
grep -q "2.8" "$FDIR/x_full.md" && ok "full export 指标可见" || bad "full export 丢指标"
grep -q "备孕" "$FDIR/x_full.md" && ok "full export entities 备孕可见" || bad "full export 丢备孕"
# viz 健康表格（full local）：列头/好转徽标/跨院仅供参考/横滑 CSS
HT="$(mktemp -d)"; mkdir -p "$HT/profile"
cp "$HX/ME.md" "$HT/ME.md"
cat > "$HT/profile/health.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
source: declared
updated: 2026-10-22
audience: local
---
## 过敏
- 青霉素过敏
## 最新关键指标
- 指标 ldl_c | 数值 2.8 | 单位 mmol/L | 参考 <3.4 | 日期 2026-10-01 | 机构 甲院 | 方法 酶法 | 采血条件 空腹 | provenance imported_report | confidence confirmed
- 指标 hba1c | 数值 6.1 | 单位 % | 参考 4.0-6.0 | 日期 2026-10-01 | 机构 乙院 | 方法 高效液相 | 采血条件 空腹 | provenance imported_report | confidence confirmed
## 结论区
- followup_due: 2027-04-01
## 历史快照（append-only）
### 2025-10-01 甲院
- 指标 ldl_c | 数值 3.6 | 单位 mmol/L | 参考 <3.4 | 日期 2025-10-01 | 机构 甲院 | 方法 酶法 | 采血条件 空腹 | provenance imported_report | confidence confirmed
EOF
cp "$HX/CONSENT-health.md" "$HT/CONSENT-health.md"
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$HT" --view profile --audience local --out "$FDIR/ht.html"
grep -q "htable" "$FDIR/ht.html" && ok "viz 表格含 htable" || bad "viz 表格缺 htable"
grep -q "最新值" "$FDIR/ht.html" && ok "viz 表格含最新值列" || bad "viz 表格缺最新值列"
grep -q "本院参考" "$FDIR/ht.html" && ok "viz 表格含本院参考列" || bad "viz 表格缺本院参考列"
grep -q "趋势" "$FDIR/ht.html" && ok "viz 表格含趋势列" || bad "viz 表格缺趋势列"
grep -q "已恢复" "$FDIR/ht.html" && ok "viz 表格 resolved 徽标" || bad "viz 表格缺 resolved 徽标"
grep -q "仅供参考" "$FDIR/ht.html" && ok "viz 表格跨院仅供参考" || bad "viz 表格缺仅供参考"
grep -q "复查到期" "$FDIR/ht.html" && ok "viz 表格复查到期" || bad "viz 表格缺复查到期"
grep -q "overflow-x:auto" "$FDIR/ht.html" && ok "390 表格横滑不溢出 CSS 在" || bad "缺横滑 CSS"
# facts_only viz 不出表
cat > "$HT/CONSENT-health.md" <<'EOF'
---
scope: facts_only
granted: true
granted_date: 2026-10-01
source: user_session
updated: 2026-10-01
---
EOF
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$HT" --view profile --audience local --out "$FDIR/ht_fo.html"
grep -q '"health_table"' "$FDIR/ht_fo.html" && bad "facts_only viz 仍注入指标表数据" || ok "facts_only viz 0 指标表数据"
# 08 提取协议存在且不含 PDF 自动导入承诺
grep -q "提取协议" "$HERE/references/08-health-extraction.md" && ok "08 提取协议文档存在" || bad "缺 08"
grep -qiE "import_pdf_report|pdfplumber|tesseract" "$HERE/references/08-health-extraction.md" && bad "08 仍承诺 PDF 导入器" || ok "08 不内置 PDF 导入器"

echo "== v13 纯文档/结构断言：09 蓝本七要素+财务第二领域；SKILL 召回正/反例固定表；08 理论锚点 =="
B9="$HERE/references/09-domain-blueprint.md"
[ -f "$B9" ] && ok "09 蓝本文件存在" || { bad "缺 09-domain-blueprint.md"; }
for kw in "领域分片" "敏感层映射" "本地授权档" "提取协议" "append-only" "最小切片" "不越界"; do
  grep -q "$kw" "$B9" && ok "09 含七要素关键词：$kw" || bad "09 缺要素：$kw"
done
grep -q "财务" "$B9" && ok "09 含财务第二领域示例" || bad "09 缺财务第二领域"
grep -q "不实现 FHIR" "$B9" && ok "09 声明不实现协议" || bad "09 缺不实现协议声明"
# 召回两张固定表下沉到 08（SKILL.md 只留四分支与口语锚点，控制在 200 行内）
grep -q "### 召回正例（应进入本技能）" "$HERE/references/08-health-extraction.md" && ok "08 召回正例固定标记" || bad "缺召回正例标记"
grep -q "### 召回反例（不进入，仅公共科普）" "$HERE/references/08-health-extraction.md" && ok "08 召回反例固定标记" || bad "缺召回反例标记"
grep -q "08-health-extraction" "$HERE/SKILL.md" && ok "SKILL 指向 08 召回完整版" || bad "SKILL 未指向 08"
for kw in "体检报告" "化验单" "存起来" "指标趋势"; do
  grep -q "$kw" "$HERE/SKILL.md" && ok "召回正例锚点：$kw" || bad "缺正例锚点：$kw"
done
for kw in "吃什么好" "体检前" "名词"; do
  grep -q "$kw" "$HERE/SKILL.md" && ok "召回反例锚点：$kw" || bad "缺反例锚点：$kw"
done
grep -q "本人档案归属" "$HERE/SKILL.md" && ok "SKILL 召回判定准则（本人归属）" || bad "缺召回判定准则"
# 08 理论锚点：借思想不实现 + RCV/EP28 原则词
grep -q "不实现 FHIR" "$HERE/references/08-health-extraction.md" && ok "08 声明不实现 FHIR" || bad "08 缺不实现 FHIR"
grep -q "轻量 Markdown" "$HERE/references/08-health-extraction.md" && ok "08 声明轻量 Markdown" || bad "08 缺轻量 Markdown"
grep -q "RCV" "$HERE/references/08-health-extraction.md" && ok "08 含 RCV 原则" || bad "08 缺 RCV"
grep -q "EP28" "$HERE/references/08-health-extraction.md" && ok "08 含 EP28 原则" || bad "08 缺 EP28"
# v14 ③ 四分支召回：已授权个性化 / 未授权轻邀请 / 家人 / 纯公共
grep -q "四分支" "$HERE/SKILL.md" && ok "SKILL 四分支召回" || bad "缺四分支"
grep -q "已存在健康授权" "$HERE/SKILL.md" && ok "分支1 已授权直接个性化" || bad "缺已授权个性化"
grep -q "一次轻邀请" "$HERE/SKILL.md" && ok "分支2 未授权一次轻邀请" || bad "缺轻邀请"
grep -q "我这个体检报告" "$HERE/SKILL.md" && ok "正例：我这个体检报告（材料在场先授权）" || bad "缺正例 我这个体检报告"
grep -q "平时吃点啥" "$HERE/SKILL.md" && ok "反例：平时吃点啥（公共科普）" || bad "缺反例 平时吃点啥"
grep -q "要不要紧" "$HERE/SKILL.md" && ok "反例：要不要紧（公共科普）" || bad "缺反例 要不要紧"
grep -q "头晕" "$HERE/SKILL.md" && ok "反例：一次性症状头晕" || bad "缺一次性症状反例"
grep -q "先取得对方知情" "$HERE/SKILL.md" && ok "家人材料先取得对方知情" || bad "缺家人知情边界"
# v14 ① 三级置信文档锚点（08/09）
grep -q "中置信" "$HERE/references/08-health-extraction.md" && ok "08 三级置信中置信软方向" || bad "08 缺中置信"
grep -q "单位可换算归一\|单位可归一" "$HERE/references/08-health-extraction.md" && ok "08 单位归一" || bad "08 缺单位归一"
grep -q "三级置信" "$B9" && ok "09 三级置信要素" || bad "09 缺三级置信"
# v14 ② 拍饭逐顿不记（05/08/body 模板）
grep -q "逐顿" "$HERE/references/05-write-protocol.md" && ok "05 拍饭逐顿不记" || bad "05 缺拍饭规则"
grep -q "周期摘要" "$HERE/references/08-health-extraction.md" && ok "08 周期摘要可选" || bad "08 缺周期摘要"
grep -q "周期跟踪摘要" "$HERE/templates/profile/body.md" && ok "body 模板周期摘要区" || bad "body 缺周期摘要区"
# v14 ④ 授权轻量化 + style + 读写上云小表
grep -q "style" "$HERE/templates/CONSENT-health.md" && ok "CONSENT 模板含 style 可选字段" || bad "CONSENT 缺 style"
grep -q "一次授权长期有效\|授权轻量化" "$HERE/SKILL.md" && ok "SKILL 授权轻量化" || bad "SKILL 缺授权轻量化"
grep -q "读 / 写 / 上云" "$HERE/references/06-privacy-family.md" && ok "06 读写上云小表" || bad "06 缺小表"
# v14 ⑤ watchlist 关注因子文档锚点（08 机制+理论 / 09 通用要素 / 模板小节 / gate 不越界说明）
grep -q "关注因子（watchlist）" "$HERE/references/08-health-extraction.md" && ok "08 watchlist 机制" || bad "08 缺 watchlist"
grep -q "1 + X\|1+X\|个体化加项" "$HERE/references/08-health-extraction.md" && ok "08 1+X 个体化锚点" || bad "08 缺1+X锚点"
grep -q "共同决策\|shared decision" "$HERE/references/08-health-extraction.md" && ok "08 SDM 锚点" || bad "08 缺 SDM"
grep -q "活动问题清单\|关注因子" "$B9" && ok "09 通用关注因子要素" || bad "09 缺关注因子要素"
grep -q "关注因子（watchlist）" "$HERE/templates/profile/health.md" && ok "health 模板含 watchlist 小节" || bad "health 模板缺 watchlist"
grep -q "WATCHLIST-SCOPE\|关注因子仅在健康" "$HERE/scripts/gate.py" && ok "gate watchlist 不越界说明" || bad "gate 缺不越界说明"
# P2-3 09 freshness/复核周期通用要素
grep -q "freshness" "$B9" && ok "09 含 freshness/复核周期要素" || bad "09 缺 freshness 要素"
grep -q "checkup" "$B9" && ok "09 挂钩 v11 checkup" || bad "09 缺 checkup 挂钩"

echo "== v12 ⑫ P1-R1 facts_only 句内（子句级）过滤：混合句只留安全事实，备孕/坐骨/焦虑=0；P2-R1 实体健康分区过授权 =="
HN="$(mktemp -d)"; mkdir -p "$HN/profile" "$HN/entities"
cat > "$HN/ME.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: identity
source: declared
updated: 2026-10-22
---
# 张三
EOF
cat > "$HN/network.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: network
layer: L2
domain: network
source: declared
updated: 2026-10-22
---
## 核心圈
- spouse 配偶；最该记住：青霉素过敏、正在备孕
- 不要公开提她工作压力/有坐骨神经痛
EOF
cat > "$HN/entities/spouse.md" <<'EOF'
---
schema: personal-context/v1
entity: spouse
type: person
layer: L2
domain: family
source: declared
circle: close
updated: 2026-10-22
---
## 基本
- 称呼：配偶
## 身体情况
- 在服降压药，有焦虑病史
EOF
cat > "$HN/CONSENT-health.md" <<'EOF'
---
scope: facts_only
granted: true
granted_date: 2026-10-01
source: user_session
updated: 2026-10-01
---
EOF
# gate network local/cloud：安全事实可在，非安全健康内容=0
out=$($PY "$HERE/scripts/gate.py" --data "$HN" --domain network --audience local --emit 2>&1) || true
echo "$out" | grep -qE "备孕|坐骨|焦虑" && bad "gate local 混合句漏非安全健康" || ok "gate local 备孕/坐骨/焦虑=0"
echo "$out" | grep -q "青霉素" && ok "gate local 保留过敏安全事实" || bad "gate local 丢过敏"
out=$($PY "$HERE/scripts/gate.py" --data "$HN" --domain network --audience cloud --emit 2>&1) || true
echo "$out" | grep -qE "备孕|坐骨|焦虑" && bad "gate cloud network 漏非安全健康" || ok "gate cloud network 备孕/坐骨/焦虑=0"
echo "$out" | grep -q "青霉素" && ok "gate cloud 保留过敏安全事实" || bad "gate cloud 丢过敏"
# export md：青霉素=1，备孕/坐骨/焦虑=0，降压药=1
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HN" --all-layers --out "$FDIR/r1.md"
grep -q "青霉素" "$FDIR/r1.md" && ok "export md 保留过敏" || bad "export md 丢过敏"
expect_grep0 "备孕" "$FDIR/r1.md"
expect_grep0 "坐骨" "$FDIR/r1.md"
expect_grep0 "焦虑" "$FDIR/r1.md"
grep -q "降压药" "$FDIR/r1.md" && ok "export md 保留在服药安全事实" || bad "export md 丢服药"
# export zip：network/spouse 同样裁剪
expect_rc 0 $PY "$HERE/scripts/export.py" --data "$HN" --format zip --all-layers --out "$FDIR/r1.zip"
( cd "$FDIR" && unzip -p r1.zip network.md 2>/dev/null | grep -qE "备孕|坐骨|焦虑" ) && bad "zip network 漏非安全健康" || ok "zip network 备孕/坐骨/焦虑=0"
( cd "$FDIR" && unzip -p r1.zip entities/spouse.md 2>/dev/null | grep -q "焦虑" ) && bad "zip spouse 漏焦虑" || ok "zip spouse 焦虑=0"
( cd "$FDIR" && unzip -p r1.zip network.md 2>/dev/null | grep -q "青霉素" ) && ok "zip network 保留过敏" || bad "zip network 丢过敏"
( cd "$FDIR" && unzip -p r1.zip entities/spouse.md 2>/dev/null | grep -q "降压药" ) && ok "zip spouse 保留服药" || bad "zip spouse 丢服药"
# viz facts_only：实体健康分区不渲染非安全事实（焦虑/坐骨=0），安全事实（降压药）可在
expect_rc 0 $PY "$HERE/scripts/viz.py" --data "$HN" --view profile --audience local --out "$FDIR/r1_viz.html"
expect_grep0 "焦虑" "$FDIR/r1_viz.html"
expect_grep0 "坐骨" "$FDIR/r1_viz.html"
grep -q "降压药" "$FDIR/r1_viz.html" && ok "viz 保留服药安全事实" || bad "viz 丢服药"

rm -rf "$HN"

rm -rf "$HX" "$HT"

rm -rf "$H1" "$H2" "$H3" "$H4" "$H5" "$H6" "$HF" "$HO" "$FDIR"

rm -rf "$BAD" "$REL" "$GHOST" "$LYR" "$MELOCK" "$MEBAD" "$XSS" "$MISS" "$L4D" "$EMPTY" "$VZ"

echo


echo "== v17 健康无损转写：合并项/定性项/边界/历史人话兼容/未知不当正常 =="
$PY - "$HERE" <<'PY2' && ok "健康无损解析与状态判定" || bad "健康无损解析或状态判定错误"
import sys; sys.path.insert(0, sys.argv[1]+"/scripts")
import health_records as H
sec="""- 指标 sbp/dbp | 数值 102/63 | 单位 mmHg | 参考 诊室正常 | 日期 2026-10-15
- 指标 weight/bmi/waist | 数值 76.8 / 25.96 / 85 | 单位 kg / — / cm | 参考 BMI<24、男腹围<85（85 临界）| 日期 2026-10-15
- 指标 ua（尿酸）| 数值 456 | 单位 μmol/L | 参考 208-428（↑）| 日期 2026-10-15
- 指标 hdl_c | 数值 0.77 | 单位 mmol/L | 参考 0.78-1.81（↓临界）| 日期 2026-10-15
- 指标 尿红细胞 / 尿蛋白 / 尿隐血 | 数值 65.0↑ / ±(0.15) / ++(80) | 单位 /μl、g/L、Ery/μl | 参考 0-8、阴性、阴性 | 日期 2026-10-15
"""
r=H.metric_rows(sec); m={x['name']:x for x in r}
assert set(('systolic','diastolic','weight','bmi','waist','ua','hdl_c','urine_rbc','urine_protein','urine_occult')) <= set(m)
assert [m[x]['unit'] for x in ('weight','bmi','waist')]==['kg','—','cm']
assert H.status(m['bmi'])=='偏高' and H.status(m['waist'])=='偏高'
assert H.status(m['ua'])=='偏高' and H.status(m['hdl_c'])=='偏低'
assert H.status(m['urine_rbc'])=='偏高' and H.status(m['urine_protein'])=='临界' and H.status(m['urine_occult'])=='阳性'
assert H.status(H.make_row('x','10','U/L',''))=='待核对'
assert H.status(H.make_row('x','5','U/L','<5'))=='偏高'       # strict boundary
assert H.status(H.make_row('x','5','U/L','≤5'))=='正常'      # inclusive boundary
assert H.status(H.make_row('x','阴性','','阴性'))=='正常'
assert H.numeric('++(80)') is None and H.numeric('<5') is None
body="""## 最新关键指标
- 指标 ua | 数值 456 | 单位 μmol/L | 参考 208-428 | 日期 2026-10-15 | 机构 乙院 | provenance imported_report | confidence confirmed
## 历史快照
### 2025-12-15 甲院（空腹，imported_report，confirmed）
- 尿酸 473↑（208-428）；ALT 30（正常，2024 的 54↑ 已恢复）；尿：隐血 ++(80)、红细胞 39.4↑(0-8)、蛋白阴性
"""
latest,hist=H.sections(body); hm={x['name']:x for x in hist}
assert H.status(hm['ua'])=='偏高' and H.status(hm['alt'])=='待核对' # parenthetical old arrow must not leak
assert H.status(hm['urine_occult'])=='阳性'
assert all(x['date']=='2025-12-15' for x in hist)
PY2

V17="$(mktemp -d)"; mkdir -p "$V17/profile"
cat > "$V17/CONSENT-health.md" <<'MD'
---
schema: personal-context/v1
scope: full
granted: true
granted_date: 2026-10-23
source: user_session
updated: 2026-10-23
---
MD
cat > "$V17/profile/health.md" <<'MD'
---
schema: personal-context/v1
entity: me
type: self
layer: L3
domain: health
confidence: high
source: declared
updated: 2026-10-23
audience: local
---
## 最新关键指标
- 指标 ua | 数值 456 | 单位 μmol/L | 参考 208-428 | 日期 2026-10-15
- 指标 hdl_c | 数值 0.77 | 单位 mmol/L | 参考 0.78-1.81 | 日期 2026-10-15
- 指标 urine_protein | 数值 ±(0.15) | 单位 g/L | 参考 阴性 | 日期 2026-10-15
- 指标 x_unknown | 数值 10 | 单位 U/L | 参考  | 日期 2026-10-15
MD
$PY "$HERE/scripts/viz.py" --data "$V17" --view profile --audience local --out "$V17/v.html" >/dev/null 2>&1
for s in '尿酸' '偏高' '高密度脂蛋白 HDL-C' '偏低' '尿蛋白' '临界' '待核对'; do grep -q "$s" "$V17/v.html" || { echo "missing $s"; exit 1; }; done && ok "viz 异常/偏低/临界/待核对不丢失" || bad "viz 健康状态丢失"
rm -rf "$V17"

echo "== 紧凑图谱：固定最新路径、无重复版本、中文人物导航、保留健康历史折叠 =="
UIN="$(mktemp -d)"
$PY "$HERE/scripts/viz.py" --data "$UIN" --audience local >/dev/null 2>&1
$PY "$HERE/scripts/viz.py" --data "$UIN" --audience local >/dev/null 2>&1
$PY - "$UIN" <<'PY' && ok "默认重复生成仍只有一份最新图谱" || bad "图谱仍生成日期版本副本"
import pathlib,sys
files=sorted(x.name for x in pathlib.Path(sys.argv[1], 'exports').glob('*.html'))
assert files==['我的个人图谱.html'], files
PY
$PY - "$HERE" <<'PY' && ok "紧凑布局保留人物导航/历史展开和安全数据边界" || bad "紧凑布局入口或历史结构丢失"
import pathlib,sys
src=pathlib.Path(sys.argv[1], 'scripts/viz.py').read_text(encoding='utf-8')
assert '.person-nav' in src and 'data-person=' in src
assert 'metric-history' in src and 'history-point' in src
assert 'max-width:1800px' in src and 'graph-world' in src and 'person-search' in src
assert 'role="button"' in src and 'keydown' in src
PY
rm -rf "$UIN"

$PY - "$HERE" <<'PY' && ok "分栏与图拖拽：四六分/分隔条/无滚轮劫持" || bad "分栏或拖拽契约缺失"
import sys, pathlib
sys.path.insert(0,str(pathlib.Path(sys.argv[1], 'scripts')))
import viz
css=viz.CSS; js=viz.JS
assert 'var(--left-weight,40fr)' in css and 'var(--right-weight,60fr)' in css
assert '#net,.small-network #net{overflow:hidden;overscroll-behavior:auto' in css
assert 'column-divider' in css and "function initColumnDivider" in js
assert "'dblclick'" in js and "e.key==='Home'" in js
assert "net.scrollLeft=drag.sx" in js and "net.scrollTop=drag.sy" in js
assert "addEventListener('wheel'" not in js
PY
$PY "$HERE/tests/test_consent_preservation.py" && ok "健康四档裁剪保留非健康人物信息：单元+gate/export/zip/viz" || bad "健康授权误删非健康档案或泄露健康"

# ============ [v16] 两层结构：结论层常驻 / 过程层 journal 按需；外发层敏感词；存储交给用户 ============
echo "== v16 ① 迁移：预演不写；执行后结论层无指标明细、过程层有；合并读取逐项一致；重跑不覆盖 =="
M1="$(mktemp -d)"; mk_health_fixture "$M1" full true
cat >> "$M1/profile/health.md" <<'EOF'
- 指标 ua | 数值 480 | 单位 μmol/L | 参考 208-428 | 日期 2026-10-01 | 机构 甲院 | 方法 尿酸酶法 | 采血条件 空腹12h | provenance imported_report
## 历史快照（append-only）
### 2025-10-01 甲院
- 指标 ldl_c | 数值 3.9 | 单位 mmol/L | 参考 <3.4 | 机构 甲院 | 方法 酶法 | 采血条件 空腹 | provenance imported_report | confidence confirmed
## 变化里程碑
- 血脂饮食控制后回落（本人确认）
EOF
fp() { $PY - "$1" "$HERE" <<'PY'
import sys; sys.path.insert(0, sys.argv[2]+"/scripts")
import mectx_common as C
l, h = C.health_sections(C.read_health_body(sys.argv[1]))
k = lambda r: (r["name"], r.get("date"), r.get("raw_value"), r.get("unit"))
print(sorted(map(k, l)), sorted(map(k, h)))
PY
}
fp0=$(fp "$M1")
h0=$(shasum "$M1/profile/health.md" | cut -c1-40)
out=$($PY "$HERE/scripts/migrate.py" --data "$M1" 2>&1)
[ "$(shasum "$M1/profile/health.md" | cut -c1-40)" = "$h0" ] && [ ! -e "$M1/journal/health-metrics.md" ] \
  && ok "预演不写任何文件" || bad "预演写了文件"
expect_rc 0 $PY "$HERE/scripts/migrate.py" --data "$M1" --apply
grep -q "^## 最新关键指标\|^## 历史快照" "$M1/profile/health.md" && bad "结论层仍有指标明细" || ok "结论层已无指标明细"
grep -q "^## 当前状态" "$M1/profile/health.md" && ok "结论层新增当前状态" || bad "缺当前状态"
grep -q "尿酸：偏高" "$M1/profile/health.md" && ok "当前状态写出尿酸偏高" || bad "当前状态没写尿酸偏高"
grep -q "480" "$M1/profile/health.md" && bad "当前状态写了数值" || ok "当前状态不写数值"
grep -q "血脂饮食控制后回落" "$M1/profile/health.md" && ok "里程碑留在结论层" || bad "里程碑被挪走"
[ "$(fp "$M1")" = "$fp0" ] && ok "合并读取的最新指标与历史与迁移前逐项一致" || bad "迁移后指标/历史不一致"
ls "$M1/.migrate-backup"/*/profile/health.md >/dev/null 2>&1 && ok "迁移前原文件已备份" || bad "缺迁移备份"
expect_rc 0 $PY "$HERE/scripts/lint.py" --data "$M1"
echo "$LAST" | grep -q "指标明细还在结论层" && bad "迁移后仍提示需迁移" || ok "迁移后不再提示"
out=$($PY "$HERE/scripts/migrate.py" --data "$M1" --apply 2>&1) && rc=0 || rc=$?
echo "$out" | grep -q "无需迁移" && ok "重跑识别已迁移，不覆盖" || bad "重跑行为异常：$out"
M2="$(mktemp -d)"; mk_health_fixture "$M2" full true; mkdir -p "$M2/journal"; echo "x" > "$M2/journal/health-metrics.md"
expect_rc 2 $PY "$HERE/scripts/migrate.py" --data "$M2" --apply
rm -f "$M2/journal/health-metrics.md"
out=$($PY "$HERE/scripts/lint.py" --data "$M2" 2>&1) || true
echo "$out" | grep -q "指标明细还在结论层" && ok "未迁移的仓 lint 提示迁移" || bad "未迁移未提示"
out=$($PY "$HERE/scripts/gate.py" --data "$M2" --journal health-metrics --audience local --emit 2>&1) || true
echo "$out" | grep -q "老仓未迁移" && echo "$out" | grep -q "3.6" && ok "未迁移的仓 --journal 回落读结论层，仍拿得到数值" || bad "未迁移的仓 --journal 拿不到数值"

echo "== v16 ①b 两层一致：体检更新后当前状态没同步 → WARN；同步后不报 =="
$PY - "$M1/journal/health-metrics.md" <<'PY'
import sys, re
p = sys.argv[1]; t = open(p, encoding="utf-8").read()
t = t.replace("数值 3.6 | 单位 mmol/L", "数值 2.9 | 单位 mmol/L", 1)
open(p, "w", encoding="utf-8").write(t)
PY
out=$($PY "$HERE/scripts/lint.py" --data "$M1" 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 0 ] && ok "不同步只提醒 rc=0" || bad "不同步改了退出码 rc=$rc"
echo "$out" | grep -q "和最新体检对不上.*低密度脂蛋白" && ok "LDL 已回落但当前状态仍写偏高 → 提醒" || bad "未提醒当前状态过时：$(echo "$out" | grep 当前状态)"
sed -i '' '/低密度脂蛋白 LDL-C：偏高/d' "$M1/profile/health.md"
out=$($PY "$HERE/scripts/lint.py" --data "$M1" 2>&1) || true
echo "$out" | grep -q "和最新体检对不上" && bad "同步后仍提醒" || ok "同步后不再提醒"
$PY - "$M1/journal/health-metrics.md" <<'PY'
import sys
p = sys.argv[1]; t = open(p, encoding="utf-8").read()
open(p, "w", encoding="utf-8").write(t.replace("数值 2.9 | 单位 mmol/L", "数值 3.6 | 单位 mmol/L", 1))
PY
$PY - "$M1/profile/health.md" <<'PY'
import sys, re
p = sys.argv[1]; t = open(p, encoding="utf-8").read()
t = re.sub(r"(## 当前状态[^\n]*\n)", r"\1- 低密度脂蛋白 LDL-C：偏高（2026-10-01）\n", t, count=1)
open(p, "w", encoding="utf-8").write(t)
PY

echo "== v16 ② 过程层默认不读：domain health 只给结论；--journal 才给明细；授权与外发照旧 =="
out=$($PY "$HERE/scripts/gate.py" --data "$M1" --domain health --audience local --emit 2>&1)
echo "$out" | grep -q "当前状态" && ok "结论层可读到当前状态" || bad "结论层读不到当前状态"
echo "$out" | grep -q "480\|3\.9" && bad "默认读取带出了指标数值" || ok "默认读取不带指标数值"
out=$($PY "$HERE/scripts/gate.py" --data "$M1" --journal health-metrics --audience local --emit 2>&1)
echo "$out" | grep -q "480" && echo "$out" | grep -q "3.9" && ok "--journal 读到最新与历史数值" || bad "--journal 读不到明细"
out=$($PY "$HERE/scripts/gate.py" --data "$M1" --journal health-metrics --audience cloud --emit 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 2 ] && ! echo "$out" | grep -q "480" && ok "过程层外发未确认 rc=2 且 0 明文" || bad "过程层外发未拦 rc=$rc"
sed -i '' 's/scope: full/scope: facts_only/' "$M1/CONSENT-health.md"
out=$($PY "$HERE/scripts/gate.py" --data "$M1" --journal health-metrics --audience local --emit 2>&1) || true
echo "$out" | grep -q "480\|3\.9" && bad "facts_only 下过程层泄露数值" || ok "facts_only 下过程层不给数值"
sed -i '' 's/granted: true/granted: false/' "$M1/CONSENT-health.md"
out=$($PY "$HERE/scripts/gate.py" --data "$M1" --journal health-metrics --audience local --emit 2>&1) || true
echo "$out" | grep -q "480\|3\.9" && bad "未授权下过程层泄露数值" || ok "未授权下过程层不给数值"
sed -i '' 's/granted: false/granted: true/; s/scope: facts_only/scope: full/' "$M1/CONSENT-health.md"
out=$($PY "$HERE/scripts/gate.py" --data "$M1" --task "我尿酸高能吃海鲜吗" 2>&1) || true
echo "$out" | grep -q "journal/" && echo "$out" | grep -q "本次切片：.*journal" && bad "关键词分类误加载过程层" || ok "关键词分类不加载过程层"

echo "== v16 ③ 导出：md 永不含过程层；zip 默认不含，--include-journal 才含且仍过授权裁剪 =="
$PY "$HERE/scripts/export.py" --data "$M1" --all-layers --out "$M1/exports/a.md" >/dev/null 2>&1 || true
grep -q "480\|文件：journal/" "$M1/exports/a.md" && bad "md 导出含过程层" || ok "md 导出不含过程层"
$PY "$HERE/scripts/export.py" --data "$M1" --format zip --out "$M1/exports/a.zip" >/dev/null 2>&1 || true
# 先落变量再 grep：pipefail 下 grep -q 提前退出会让 unzip 吃 SIGPIPE，正例随机误判、反例可能掩盖真泄露
zl=$(unzip -l "$M1/exports/a.zip"); echo "$zl" | grep -q "journal/" && bad "默认 zip 含过程层" || ok "默认 zip 不含过程层"
$PY "$HERE/scripts/export.py" --data "$M1" --format zip --include-journal --out "$M1/exports/b.zip" >/dev/null 2>&1 || true
zl=$(unzip -l "$M1/exports/b.zip"); echo "$zl" | grep -q "journal/health-metrics.md" && ok "--include-journal 带上过程层" || bad "--include-journal 未带过程层"
sed -i '' 's/scope: full/scope: facts_only/' "$M1/CONSENT-health.md"
$PY "$HERE/scripts/export.py" --data "$M1" --format zip --include-journal --out "$M1/exports/c.zip" >/dev/null 2>&1 || true
( cd "$M1/exports" && unzip -p c.zip journal/health-metrics.md | grep -q "480" ) && bad "facts_only 下 zip 过程层泄露数值" || ok "facts_only 下 zip 过程层不出数值"
sed -i '' 's/scope: facts_only/scope: full/' "$M1/CONSENT-health.md"

echo "== v16 ④ viz 迁移前后健康表一致；init 铺过程层模板；全新仓 lint 通过 =="
$PY "$HERE/scripts/viz.py" --data "$M1" --out "$M1/exports/v.html" >/dev/null 2>&1 || true
grep -q "480" "$M1/exports/v.html" && ok "viz 合并读取后仍显示最新数值" || bad "viz 迁移后丢了指标"
grep -q '"history"' "$M1/exports/v.html" && grep -q "3.9" "$M1/exports/v.html" && ok "viz 仍显示历史点" || bad "viz 迁移后丢了历史"
TJ="$(mktemp -d)/d"; $PY "$HERE/scripts/init.py" --path "$TJ" >/dev/null
[ -f "$TJ/journal/health-metrics.md" ] && [ -f "$TJ/journal/decisions.md" ] && ok "init 铺过程层两份模板" || bad "init 缺过程层模板"
grep -q "^## 最新关键指标" "$TJ/profile/health.md" && bad "新仓结论层仍带指标表" || ok "新仓结论层不带指标表"
expect_rc 0 $PY "$HERE/scripts/lint.py" --data "$TJ"
grep -q "exports/" "$TJ/.gitignore" && grep -q ".migrate-backup/" "$TJ/.gitignore" && ok "gitignore 忽略导出与迁移备份" || bad "gitignore 缺项"
rm -rf "$M2" "$(dirname "$TJ")"

echo "== v16 ⑤ lint：会外发的低层文件出现健康/财务细节 → WARN；概览夹带健康 → WARN；rc 不变 =="
L1D="$(mktemp -d)"; mkdir -p "$L1D/profile"
cat > "$L1D/ME.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: self
layer: L1
domain: identity
source: declared
updated: 2026-10-22
audience: cloud-low
---
# 张三
- 索引：健康分片记着他的透析和房贷安排
EOF
cat > "$L1D/network.md" <<'EOF'
---
schema: personal-context/v1
entity: me
type: network
layer: L2
domain: network
source: declared
updated: 2026-10-22
audience: local
---
## inner
- 母亲：定期透析
EOF
out=$($PY "$HERE/scripts/lint.py" --data "$L1D" 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 0 ] && ok "敏感词只提醒不阻断 rc=0" || bad "敏感词提醒改了退出码 rc=$rc"
echo "$out" | grep "ME.md" | grep -q "默认带给外部 AI.*透析" && ok "ME.md 健康细节被提醒" || bad "ME.md 健康细节未提醒"
echo "$out" | grep "ME.md" | grep -q "房贷" && ok "ME.md 财务细节被提醒" || bad "ME.md 财务细节未提醒"
echo "$out" | grep "network.md" | grep -q "关系网概览.*透析" && ok "概览夹带健康被提醒" || bad "概览夹带健康未提醒"
printf -- "---\nschema: personal-context/v1\nentity: me\ntype: self\nlayer: L1\ndomain: work\nsource: declared\nupdated: 2026-10-22\naudience: cloud-low\n---\n# 工作\n<!-- 备注：房贷还剩两年 -->\n" > "$L1D/profile/work.md"
out=$($PY "$HERE/scripts/lint.py" --data "$L1D" 2>&1) || true
echo "$out" | grep "work.md" | grep -q "房贷" && ok "外发文件注释里的财务细节也被提醒（gate 会原样带出注释）" || bad "注释里的敏感词漏提醒"
out=$($PY "$HERE/scripts/gate.py" --data "$L1D" --domain work --audience cloud --emit 2>&1) || true
echo "$out" | grep -q "房贷" && ok "确认 gate 会带出注释，提醒有必要" || ok "gate 未带出注释"
sed -i '' 's/audience: cloud-low/audience: local/' "$L1D/ME.md"
out=$($PY "$HERE/scripts/lint.py" --data "$L1D" 2>&1) || true
echo "$out" | grep "ME.md" | grep -q "默认带给外部 AI" && bad "标了只在本机仍按外发提醒" || ok "标了只在本机不按外发提醒"
out=$($PY "$HERE/scripts/lint.py" --data "$HERE/examples" 2>&1) || true
echo "$out" | grep -q "默认带给外部 AI" && bad "虚构示例触发外发敏感提醒：$(echo "$out" | grep '默认带给外部 AI' | head -1)" || ok "虚构示例无外发敏感提醒"
mkdir -p "$L1D/journal"; printf -- "---\nlayer: L4\n---\nx\n" > "$L1D/journal/bad.md"
expect_rc 1 $PY "$HERE/scripts/lint.py" --data "$L1D"
echo "$LAST" | grep -q "L4 秘密不能放过程层" && ok "过程层放 L4 报错" || bad "过程层 L4 未报错"
rm -rf "$L1D"

echo "== v16 ⑥ 存储交给用户：技能不带版本记录/加密备份脚本，所有脚本不调 git/openssl、不联网 =="
[ ! -e "$HERE/scripts/backup.py" ] && ok "不再提供 backup.py" || bad "backup.py 仍在"
hits=$(grep -nE "urllib|requests|socket|http\.client|\"git\"|\"openssl\"" "$HERE"/scripts/*.py || true)
[ -z "$hits" ] && ok "脚本不调 git/openssl、不联网" || bad "脚本含外部调用：$hits"
rm -rf "$M1"

echo "== v16 ⑦ SKILL.md 不超 200 行；description 不超 400 字 =="
n=$(wc -l < "$HERE/SKILL.md" | tr -d ' ')
[ "$n" -le 200 ] && ok "SKILL.md $n 行（≤200）" || bad "SKILL.md $n 行（>200）"
dl=$($PY - "$HERE/SKILL.md" <<'PY'
import sys
fm = open(sys.argv[1], encoding="utf-8").read().split("---")[1]
print(next(len(l) - len("description:") for l in fm.splitlines() if l.startswith("description:")))
PY
)
[ "$dl" -le 400 ] && ok "description $dl 字（≤400）" || bad "description $dl 字（>400）"

echo "== v16 ⑧ 收口补洞：--entity 不能穿越；迁移备份不导出；新文件不放宽权限 =="
PW="$(mktemp -d)"; P1="$PW/d"; mk_health_fixture "$P1" facts_only true; mkdir -p "$P1/entities"
cat >> "$P1/profile/health.md" <<'EOF'
- 指标 ua | 数值 480 | 单位 μmol/L | 参考 208-428 | 日期 2026-10-01 | 机构 甲院 | provenance imported_report
EOF
chmod 600 "$P1/profile/health.md"
expect_rc 0 $PY "$HERE/scripts/migrate.py" --data "$P1" --apply
[ "$(stat -f %Lp "$P1/journal/health-metrics.md")" = "600" ] && ok "过程层新文件沿用原文件 600 权限" || bad "过程层新文件权限变宽：$(stat -f %Lp "$P1/journal/health-metrics.md")"
[ "$(stat -f %Lp "$P1/.migrate-backup")" = "700" ] && ok "迁移备份目录只给本人" || bad "迁移备份目录权限：$(stat -f %Lp "$P1/.migrate-backup")"
for e in "../journal/health-metrics" "../profile/health" "sub/x"; do
  out=$($PY "$HERE/scripts/gate.py" --data "$P1" --domain work --entity "$e" --audience local --emit 2>&1) && rc=0 || rc=$?
  [ "$rc" -eq 1 ] && ! echo "$out" | grep -q "480" && ok "--entity $e 被拒（rc=1，0 明文）" || bad "--entity $e 未拦 rc=$rc"
done
printf -- "---\nschema: personal-context/v1\nentity: spouse-li\ntype: person\nlayer: L2\ndomain: network\nsource: declared\nupdated: 2026-10-22\ncircle: inner\n---\n# 配偶\n- 喜欢爬山\n" > "$P1/entities/spouse-li.md"
out=$($PY "$HERE/scripts/gate.py" --data "$P1" --domain network --entity spouse-li --audience local --emit 2>&1) || true
echo "$out" | grep -q "喜欢爬山" && ok "正常实体 id 照常加载" || bad "正常实体 id 被误拦"
$PY "$HERE/scripts/export.py" --data "$P1" --format zip --out "$P1/exports/p.zip" >/dev/null 2>&1 || true
zl=$(unzip -l "$P1/exports/p.zip"); echo "$zl" | grep -q "migrate-backup" && bad "zip 带走了迁移备份" || ok "zip 不带迁移备份"
$PY "$HERE/scripts/export.py" --data "$P1" --format zip --include-journal --include-private --out "$P1/exports/q.zip" >/dev/null 2>&1 || true
zl=$(unzip -l "$P1/exports/q.zip"); echo "$zl" | grep -q "migrate-backup" && bad "完整备份 zip 带走了迁移备份" || ok "完整备份 zip 也不带迁移备份"
leak=""; for n in $(unzip -Z1 "$P1/exports/p.zip"); do zc=$(unzip -p "$P1/exports/p.zip" "$n"); echo "$zc" | grep -q "480" && leak="$leak $n"; done
[ -z "$leak" ] && ok "facts_only 下 zip 逐文件无数值" || bad "facts_only 下 zip 泄露数值：$leak"
expect_rc 0 $PY "$HERE/scripts/lint.py" --data "$P1"
echo "$LAST" | grep -q "migrate-backup" && bad "lint 扫了迁移备份" || ok "lint 不扫迁移备份"
rm -rf "$PW"

echo "== v16 ⑨ 二轮验收补洞：概览财务也提醒；relations 备注提醒；行内注释不让 local 失效；目录链接不跟；md/viz 认 local；只读文件迁移回退 =="
QW="$(mktemp -d)"; Q="$QW/d"; mkdir -p "$Q/profile" "$Q/entities"
printf -- "---\nschema: personal-context/v1\nentity: me\ntype: self\nlayer: L1\ndomain: identity\nsource: declared\nupdated: 2026-10-22\naudience: cloud-low\n---\n# 张三\n" > "$Q/ME.md"
printf -- "---\nschema: personal-context/v1\nentity: me\ntype: network\nlayer: L2\ndomain: network\nsource: declared\nupdated: 2026-10-22\naudience: local\n---\n## inner\n- 父母：房贷还剩 30 万，月供 5000\n" > "$Q/network.md"
printf -- "---\nschema: personal-context/v1\nentity: me\ntype: relation\nlayer: L1\ndomain: relations\nsource: declared\nupdated: 2026-10-22\naudience: cloud-low\n---\n- from: me\n  type: knows\n  to: me\n  note: 母亲透析中\n" > "$Q/relations.md"
out=$($PY "$HERE/scripts/lint.py" --data "$Q" 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 0 ] && ok "提醒不改退出码 rc=0" || bad "提醒改了退出码 rc=$rc"
echo "$out" | grep "network.md" | grep -q "关系网概览.*财务.*房贷" && ok "关系网概览里的财务细节也提醒" || bad "概览财务细节未提醒：$(echo "$out" | grep network.md)"
echo "$out" | grep "relations.md" | grep -q "默认带给外部 AI.*透析" && ok "relations.md 备注里的健康细节提醒" || bad "relations 备注未提醒"
sed -i '' 's/^audience: cloud-low$/audience: local/' "$Q/relations.md"
out=$($PY "$HERE/scripts/lint.py" --data "$Q" 2>&1) || true
echo "$out" | grep -q "relations.md.*默认带给外部 AI" && bad "relations 标了只在本机仍按外发提醒" || ok "relations 标了只在本机不再提醒"
# 行内注释：audience: local  # ... 仍按只在本机处理；CONSENT 模板只改值不删注释也生效
printf -- "---\nschema: personal-context/v1\nentity: me\ntype: self\nlayer: L1\ndomain: work\nsource: declared\nupdated: 2026-10-22\naudience: local   # 只在本机\n---\n- 本机工作备注QK1\n" > "$Q/profile/work.md"
out=$($PY "$HERE/scripts/gate.py" --data "$Q" --domain work --audience cloud --emit 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 2 ] && ! echo "$out" | grep -q "QK1" && ok "audience 带行内注释仍拦（rc=2，0 明文）" || bad "行内注释让 local 失效 rc=$rc"
sed 's/^scope: off /scope: full/; s/^granted: false/granted: true/' "$HERE/templates/CONSENT-health.md" > "$Q/CONSENT-health.md"
out=$($PY "$HERE/scripts/gate.py" --data "$Q" --check-consent 2>&1)
echo "$out" | grep -q "scope=full" && ok "CONSENT 模板保留注释改成 full 能生效" || bad "CONSENT 模板行内注释导致授权读不出：$out"
# md 导出与 viz 脱敏版：标了 local 的 L1 文件和 gate 一致，默认不带
$PY "$HERE/scripts/export.py" --data "$Q" --out "$QW/e.md" >/dev/null 2>&1 || true
grep -q "QK1" "$QW/e.md" && bad "默认 md 导出带出了只在本机的文件" || ok "默认 md 导出不带只在本机的 L1 文件"
$PY "$HERE/scripts/export.py" --data "$Q" --all-layers --out "$QW/e2.md" >/dev/null 2>&1 || true
grep -q "QK1" "$QW/e2.md" && ok "--all-layers 才带只在本机的文件" || bad "--all-layers 也不带"
[ "$(stat -f %Lp "$QW/e.md")" = "600" ] && ok "md 导出产物只给本人" || bad "md 导出产物权限：$(stat -f %Lp "$QW/e.md")"
$PY "$HERE/scripts/viz.py" --data "$Q" --audience cloud --out "$QW/c.html" >/dev/null 2>&1 || true
grep -q "QK1" "$QW/c.html" && bad "viz 脱敏版带出了只在本机的文件" || ok "viz 脱敏版不带只在本机的 L1 文件"
$PY "$HERE/scripts/viz.py" --data "$Q" --audience local --out "$QW/l.html" >/dev/null 2>&1 || true
grep -q "QK1" "$QW/l.html" && ok "viz 本地版照常显示" || bad "viz 本地版误锁"
[ "$(stat -f %Lp "$QW/l.html")" = "600" ] && ok "viz 本地版产物只给本人" || bad "viz 产物权限：$(stat -f %Lp "$QW/l.html")"
# 目录符号链接：entities/ 指向 journal/、profile/ 指向仓外，都不跟
mkdir -p "$Q/journal" "$QW/outside"
printf -- "---\nschema: personal-context/v1\nentity: x\ntype: person\nlayer: L2\ndomain: network\nsource: declared\nupdated: 2026-10-22\ncircle: inner\n---\n- 过程层秘密JNL2\n" > "$Q/journal/x.md"
rmdir "$Q/entities"; ln -s "$Q/journal" "$Q/entities"
out=$($PY "$HERE/scripts/gate.py" --data "$Q" --domain network --entity x --audience local --emit 2>&1) && rc=0 || rc=$?
[ "$rc" -eq 1 ] && ! echo "$out" | grep -q "JNL2" && ok "entities/ 是链接时 --entity 拒绝（rc=1，0 明文）" || bad "--entity 跟了目录链接 rc=$rc"
$PY "$HERE/scripts/export.py" --data "$Q" --all-layers --out "$QW/e3.md" >/dev/null 2>&1 || true
grep -q "JNL2" "$QW/e3.md" && bad "md 导出跟了 entities 目录链接" || ok "md 导出不跟 entities 目录链接"
$PY "$HERE/scripts/viz.py" --data "$Q" --audience local --out "$QW/l2.html" >/dev/null 2>&1 || true
grep -q "JNL2" "$QW/l2.html" && bad "viz 跟了 entities 目录链接" || ok "viz 不跟 entities 目录链接"
rm "$Q/entities"; mkdir -p "$Q/entities"
printf -- "---\nschema: personal-context/v1\nentity: me\ntype: self\nlayer: L1\ndomain: work\nsource: declared\nupdated: 2026-10-22\n---\n- 仓外秘密OUT1\n" > "$QW/outside/work.md"
mv "$Q/profile" "$Q/profile.real"; ln -s "$QW/outside" "$Q/profile"
out=$($PY "$HERE/scripts/gate.py" --data "$Q" --domain work --audience local --emit 2>&1) || true
echo "$out" | grep -q "OUT1" && bad "gate 跟了 profile 目录链接读到仓外" || ok "gate 不跟 profile 目录链接"
$PY "$HERE/scripts/export.py" --data "$Q" --all-layers --out "$QW/e4.md" >/dev/null 2>&1 || true
grep -q "OUT1" "$QW/e4.md" && bad "md 导出跟了 profile 目录链接" || ok "md 导出不跟 profile 目录链接"
rm "$Q/profile"; mv "$Q/profile.real" "$Q/profile"
# viz cloud：标了 audience: local（含行内注释）的实体整人正文锁住；local 照常显示
EV="$QW/ev"; mkdir -p "$EV/profile" "$EV/entities"; cp "$Q/ME.md" "$EV/ME.md"
printf -- "---\nschema: personal-context/v1\nentity: spouse-li\ntype: person\nlayer: L1\ndomain: network\nsource: declared\nupdated: 2026-10-22\ncircle: inner\naudience: local  # 只本机\n---\n# 配偶\n- 本名：李真名ENT\n- 爱好：ENTLOC1\n" > "$EV/entities/spouse-li.md"
printf -- "---\nschema: personal-context/v1\nentity: child-1\ntype: person\nlayer: L3\ndomain: network\nsource: declared\nupdated: 2026-10-22\ncircle: inner\n---\n# 孩子\n- 爱好：ENTL3X\n" > "$EV/entities/child-1.md"
printf -- "---\nschema: personal-context/v1\nentity: friend-a\ntype: person\nlayer: L1\ndomain: network\nsource: declared\nupdated: 2026-10-22\ncircle: friends\n---\n# 朋友\n- 爱好：ENTOPEN1\n" > "$EV/entities/friend-a.md"
$PY "$HERE/scripts/viz.py" --data "$EV" --audience cloud --out "$QW/ec.html" >/dev/null 2>&1 || true
$PY "$HERE/scripts/viz.py" --data "$EV" --audience local --out "$QW/el.html" >/dev/null 2>&1 || true
grep -q "ENTLOC1\|李真名ENT" "$QW/ec.html" && bad "viz 脱敏版带出了标 local 的实体正文" || ok "viz 脱敏版锁住标 local 的实体（含行内注释）"
grep -q "ENTOPEN1" "$QW/ec.html" && ok "viz 脱敏版照常显示普通实体" || bad "viz 脱敏版误锁普通实体"
grep -q "ENTLOC1" "$QW/el.html" && grep -q "ENTL3X" "$QW/el.html" && ok "viz 本地版照常显示这些实体" || bad "viz 本地版误锁实体"
# 迁移：health.md 只读时写入失败 → 回退，不留半截过程层
MR="$QW/ro"; mk_health_fixture "$MR" full true
chmod 400 "$MR/profile/health.md"; h0=$(shasum "$MR/profile/health.md" | cut -c1-40)
expect_rc 1 $PY "$HERE/scripts/migrate.py" --data "$MR" --apply
echo "$LAST" | grep -q "回退" && ok "只读文件写入失败报回退" || bad "只读文件未报回退"
[ ! -e "$MR/journal/health-metrics.md" ] && [ "$(shasum "$MR/profile/health.md" | cut -c1-40)" = "$h0" ] \
  && ok "回退后无半截过程层、原文件不变" || bad "回退后残留过程层或原文件被改"
[ ! -e "$MR/.migrate-backup" ] && ok "回退后不留这次的迁移备份" || bad "回退后残留迁移备份"
chmod 600 "$MR/profile/health.md"; printf -- "- 2026-10-23 me        旧记录" > "$MR/CHANGELOG.md"
expect_rc 0 $PY "$HERE/scripts/migrate.py" --data "$MR" --apply
tail -1 "$MR/CHANGELOG.md" | grep -q "^- [0-9-]* me  *结构迁移" && [ "$(grep -c '^- ' "$MR/CHANGELOG.md")" = "2" ] \
  && ok "CHANGELOG 按原格式追加一行，不吞上一行" || bad "CHANGELOG 追加格式不对：$(tail -2 "$MR/CHANGELOG.md")"
# lint --checkup 不扫迁移备份
out=$($PY "$HERE/scripts/lint.py" --data "$MR" --checkup 2>&1) || true
echo "$out" | grep -q "migrate-backup" && bad "checkup 扫了迁移备份" || ok "checkup 不扫迁移备份"
rm -rf "$QW"

if command -v node >/dev/null 2>&1; then
  node "$HERE/tests/test_graph_model.js" && ok "多人多层图模型反例通过" || bad "图模型反例失败"
  node "$HERE/tests/test_viewport_events.js" && ok "缩窗/多指/丢失捕获事件反例通过" || bad "视口事件边界回归失败"
else
  echo "SKIP 图模型 Node 单元测：运行技能无需 Node，维护验收机需补测"
fi
echo "================ 结果：PASS=$PASS FAIL=$FAIL ================"
rm -rf "$WORK" "$TMP" /tmp/work_nofm.md /tmp/empty /tmp/n.zip
[ "$FAIL" -eq 0 ] || exit 1
