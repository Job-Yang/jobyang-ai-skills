# 01 · 采集科学依据与许可清单

> **【产品定位 v2 · 先读】本技能是"个人助理向用户做入职情况了解"，不是心理测评。**
> 默认 onboarding 采集的是**显式事实与协作偏好**（行业/作息/过敏禁忌/回答要先给结论还是先分析…），
> 依据是显式上下文有用（LaMP 系列）、行为规格越具体越好（1/25 法则）、可辩驳即可改（contestable）。
>
> **决策演进**：v1 误把 Mini-IPIP 等量表当快速档主体，用户实测强烈反馈"做成心理测试、跑偏了"，
> 还把反向计分/因子/偏高居中偏低这类内部机制漏给了用户。v2 起：
> - 默认三档题本（`templates/questions/bootstrap.md`）**不含任何量表题**，性格只收用户自报标签（user-declared self-tag，
>   如 ENTP/急脾气——不是测量、不假装科学、可随时改）。
> - 下方关于大五/量表的内容保留为**理论与许可参考**（白皮书仍引用 LaMP/1-25/contestable/大五效度等结论），
>   但默认产品流程不再跑量表；仅当用户明确想做学术自评时，才从文末附录链接取题、作弱参考。
> - 理由：个人助理要的是事实与协作指令，特质分对具体服务增益弱、且像考试；自报标签更省力。

---

> （以下为早期测量学讨论与许可清单，保留作附录性质的参考，不用于默认 onboarding。）
> 短量表在 20–30 分钟内**只能可靠地立"大五领域级粗轮廓 + 价值象限 + 决策倾向 hint"**，测不了细面、分域风险、依恋、职业锚。

---

## 1. 测什么 / 不测什么（边界先讲清）

**能测（粗方向）：**
- 大五（N/E/O/A/C）**领域级**粗轮廓：这个人偏哪个方向。每维 4 题（Mini-IPIP）只给方向感。
- 价值取向两轴四高阶象限的粗方向（自我增强↔自我超越、保守↔求变）。
- 决策风格弱信号 hint（理性/直觉/回避）。

**不能测（一律不下结论）：**
- facet/面级刻画（30 题内结构上不可能，需 IPIP-NEO 30 面题库，留待精测）。
- "一个总分的风险偏好"——风险必须分域（敢蹦极者未必敢炒股）。
- 成人依恋（ECR-S 12 题起）、HEXACO-H 诚实-谦逊（≥10 题）、RIASEC 六型（60 题起）、Schein 职业锚——短测信度塌缩；**默认 onboarding 与事实型领域包均不使用**，仅当用户明确要做学术/职业自评时见文末附录（非默认，只给官方链接）。

**粗测非诊断声明**：每维 4 题 α≈.65–.77，中位点附近区分度最差；输出只允许"偏高/居中/偏低"三级方向词，**不做 facet 刻画、不做临床诊断、不与任何国籍常模比较下结论**。

---

## 2. 各量表信效度一句话 + 许可 + 中文版 + 本技能用途

| 量表 | 一句话信效度 | 授权许可 | 中文版 | 本技能用途 |
|---|---|---|---|---|
| **Mini-IPIP**（Donnellan 2006，20 题） | 每维 4 题，α=.65–.77，只够个体粗定位 | **公共域**：可复制/修改/翻译/商用，无需许可费用 | 无官方逐字版（本仓为自译待验证） | **标准档大五粗测核心**，全文入仓 |
| TIPI（Gosling 2003，10 题） | 每维 2 题，α=.40–.73，作者自认偏粗 | 官方：任何人任何用途免费 | 有流传（李金德 TIPI-C） | **不采用**（测量学不推荐，非许可问题） |
| BFI-2 / -S / -XS | XS=15 题，作者明示只够粗筛 | 免费非商业学术（Soto & John 版权） | 有四样本验证 | 备选，**不放题本**，只给链接 |
| HEXACO-PI-R | H 维需 ≥10 题才够 | 免费非营利学术下载 | 有翻译、缺顶级验证 | 伦理包，不入 bootstrap，只给链接 |
| Schwartz PVQ / PVQ-21 | 10 基本价值观环形结构 | ESS 免费供**非商业学术**；题本版权归 Schwartz，**非公共域** | 使用广泛 | **非默认附录**：用户明确想做价值观自评才从官方取，不放题本 |
| GDMS（Scott & Bruce 1995，25 题） | 每风格 5 题，α≈.70–.80 | 期刊版权（SAGE），用需版权人许可 | 有验证 | **非默认附录**，只给链接；默认流程不做决策风格探测 |
| DOSPERT（Blais & Weber，30 题） | 风险必须分域（5 域×6） | Columbia：可使用但要求引用，未给开源许可 | 谢晓非等 2012 中文验证 | **非默认附录**，只给链接；健康/财务分片只记事实，不做风险分域细评 |
| O*NET Interest Profiler（RIASEC） | 短版 60 题 | **CC BY-ND 4.0**：可逐字转载、须署名 USDOL/ETA、禁改写题面 | 有修订 | **非默认附录**；职业分片只记履历/技能/规划事实 |
| ECR / ECR-S（成人依恋） | ECR-S 12 题起 | 非商业研究免费，**商用需作者许可** | 李同归中文版 | **非默认附录**，只给链接 |
| NEO-PI-R / NEO-FFI | 大五金标准 | **商业付费**（PAR） | — | 不采用 |
| Schein 职业锚 COI | 反思框架、非严格测量 | **商业出版**（Wiley/Pfeiffer） | — | **非默认附录**，不放题本 |
| DISC / MBTI | 类型学：重测约一半人翻转二分维；无绩效预测效度元分析 | 商业 | — | 不采用 |

---

## 3. 公共域与版权清单（红线）

**可入 MIT 开源仓的题本：**
- ✅ **Mini-IPIP 20 题英文原题全文**（公共域）——IPIP 官网逐字声明：
  > "The items and scales are in the public domain, which means that one can copy, edit, translate, or use them for any purpose without asking permission and without paying a fee."
  - 官方键：https://ipip.ori.org/MiniIPIPKey.htm
  - 公共域声明：https://ipip.ori.org/index.htm
  - 引用：Donnellan et al. (2006) + IPIP（http://ipip.ori.org/）。
- ✅ **me-context 事实/偏好采集题**（称呼/工作/作息/过敏禁忌/协作方式/自报标签等）——本仓自有版权，随 MIT 发布。默认流程无任何量表题。

**不进本仓、只给官方链接的版权题本：**
- ❌ PVQ/PVQ-21（Schwartz）→ ESS 源问卷页 https://www.europeansocialsurvey.org/methodology/ess-methodology/source-questionnaire
- ❌ GDMS 全 25 题 → SAGE https://journals.sagepub.com/doi/10.1177/0013164495055006009
- ❌ DOSPERT 全题本 → Columbia CDS https://business.columbia.edu/cds/research/research-tools/dospert-scale
- ❌ ECR/ECR-S → Fraley lab https://labs.psychology.illinois.edu/~rcfraley/measures/ecrr.htm
- ❌ BFI-2 系列 → Berkeley John Lab https://www.ocf.berkeley.edu/~johnlab/bfi.html
- ❌ HEXACO-PI-R → https://hexaco.org/hexaco-inventory
- ❌ NEO / Schein 职业锚 → 商业付费，禁止。

> 即：题库里只有公共域（Mini-IPIP 20 题全文）+ 本仓原创题；其余版权量表一律"结构说明 + 官方获取链接 + 至多 1–3 题明确标注的引用示例"。
