(() => {
  "use strict";

  const root = document.querySelector(".rf-shell");
  const canvas = document.querySelector(".rf-canvas");
  const board = document.querySelector(".rf-board");
  const manifestNode = document.querySelector("#review-manifest");

  if (!root || !canvas || !board || !manifestNode) {
    throw new Error("设计工作台缺少 shell、canvas、board 或 review-manifest。");
  }

  const rawManifest = JSON.parse(manifestNode.textContent);
  const workspace = {
    layout: "spatial-studio/v1",
    leftResources: ["pages", "states", "assets", "outputs"],
    reviewModes: ["experience", "explain", "comment", "compare"],
    narrowPanelPolicy: "exclusive",
    contextDock: true,
    ...(rawManifest.workspace || {}),
  };
  const project = rawManifest.project || {};
  const legacyStage = rawManifest.stage || {};
  const stages = (rawManifest.stages?.length ? rawManifest.stages : [legacyStage])
    .filter((stage) => stage?.id)
    .map((stage, index) => ({
      id: stage.id,
      title: stage.title || `关卡 ${index + 1}`,
      summary: stage.summary || "",
      confirm: stage.confirm || "确认当前内容符合预期。",
      status: stage.status || (index === 0 ? "active" : "idle"),
      defaultPageId: stage.defaultPageId || "all",
      defaultVariantId: stage.defaultVariantId || "all",
    }));

  const legacyPages = rawManifest.pages || [];
  const manifestArtboards = rawManifest.artboards?.length
    ? rawManifest.artboards
    : legacyPages.map((page) => ({
      ...page,
      id: page.id,
      stageId: legacyStage.id || stages[0]?.id || "unknown",
      pageId: page.id,
      pageTitle: page.title,
      variantId: "base",
      variantTitle: "当前方案",
    }));

  const domArtboards = [...board.querySelectorAll(".rf-page[data-review-page]")];
  const artboards = manifestArtboards.map((item, index) => {
    const stageId = item.stageId || stages[0]?.id || "unknown";
    return {
      ...item,
      id: item.id || `${stageId}-${item.pageId || index + 1}-${item.variantId || "base"}`,
      stageId,
      pageId: item.pageId || item.id,
      pageTitle: item.pageTitle || item.title || item.pageId || `页面 ${index + 1}`,
      variantId: item.variantId || "base",
      variantTitle: item.variantTitle || "当前方案",
      title: item.title || item.pageTitle || item.pageId || `画板 ${index + 1}`,
      summary: item.summary || "",
      modules: item.modules || [],
    };
  });

  domArtboards.forEach((node, index) => {
    const declaredId = node.dataset.reviewArtboard;
    const legacyPageId = node.dataset.reviewPage;
    const match = artboards.find((item) => item.id === declaredId)
      || artboards.find((item) => item.pageId === legacyPageId && !item._bound)
      || artboards[index];
    if (!match) return;
    match._bound = true;
    node.dataset.reviewArtboard = match.id;
    node.dataset.reviewStage = match.stageId;
    node.dataset.reviewPage = match.pageId;
    node.dataset.reviewVariant = match.variantId;
    node.dataset.reviewPageTitle = match.title;
    node.dataset.prototypeState ||= "default";
  });

  const artboardMap = new Map(artboards.map((item) => [item.id, item]));
  const storageKey = `design-review:${project.id || "prototype"}`;
  const workflowStorageKey = `${storageKey}:workflow`;

  const state = {
    mode: "experience",
    stageId: rawManifest.activeStageId || stages.find((stage) => stage.status === "active")?.id
      || stages[0]?.id || "unknown",
    pageId: "all",
    variantId: "all",
    compareIds: [],
    resourceTab: "pages",
    leftPanelOpen: true,
    rightPanelOpen: false,
    scale: 0.6,
    panX: 0,
    panY: 0,
    panEnabled: false,
    spacePan: false,
    draggingBoard: false,
    suppressCanvasClick: false,
    boardPointer: null,
    activeModuleKey: null,
    tourIndex: -1,
    comments: [],
    commentFilter: "open",
    activeCommentId: null,
    pendingComment: null,
    drawing: null,
    contract: null,
    workflow: {
      schema: "design-review-workflow/v1",
      projectId: project.id || "prototype",
      activeStageId: null,
      stages: {},
      selections: {},
    },
  };

  const els = {
    modes: [...document.querySelectorAll(".rf-mode[data-mode]")],
    stageList: document.querySelector("[data-role='stage-list']") || document.querySelector(".rf-flow"),
    pageList: document.querySelector("[data-role='page-list']") || document.querySelector(".rf-page-list"),
    strip: document.querySelector("[data-role='context-strip']") || document.querySelector(".rf-page-strip"),
    pageNodes: domArtboards,
    panButton: document.querySelector('[data-command="pan"]'),
    zoomLabel: document.querySelector('[data-role="zoom-label"]'),
    canvasTitle: document.querySelector('[data-role="canvas-title"]'),
    canvasSubtitle: document.querySelector('[data-role="canvas-subtitle"]'),
    canvasModeHint: document.querySelector('[data-role="canvas-mode-hint"]'),
    canvasModeTitle: document.querySelector('[data-role="canvas-mode-title"]'),
    canvasModeCopy: document.querySelector('[data-role="canvas-mode-copy"]'),
    projectTitle: document.querySelector('[data-role="project-title"]'),
    projectMeta: document.querySelector('[data-role="project-meta"]'),
    locationStage: document.querySelector('[data-role="location-stage"]'),
    locationVersion: document.querySelector('[data-role="location-version"]'),
    pageSectionTitle: document.querySelector('[data-role="page-section-title"]'),
    leftNote: document.querySelector('[data-role="left-note"]'),
    footerTitle: document.querySelector('[data-role="footer-title"]'),
    footerCopy: document.querySelector('[data-role="footer-copy"]'),
    confirmButton: document.querySelector('[data-command="stage-confirm"]'),
    variantDecision: document.querySelector('[data-role="variant-decision"]'),
    variantDecisionTitle: document.querySelector('[data-role="variant-decision-title"]'),
    variantDecisionState: document.querySelector('[data-role="variant-decision-state"]'),
    variantNote: document.querySelector('[data-role="variant-note"]'),
    variantSelect: document.querySelector('[data-command="variant-select"]'),
    guideKicker: document.querySelector('[data-role="guide-kicker"]'),
    guideTitle: document.querySelector('[data-role="guide-title"]'),
    guideProgress: document.querySelector('[data-role="guide-progress"]'),
    guideFacts: document.querySelector('[data-role="guide-facts"]'),
    guideIndex: document.querySelector('[data-role="guide-index"]'),
    commentList: document.querySelector('[data-role="comment-list"]'),
    commentCount: document.querySelector('[data-role="comment-count"]'),
    compareList: document.querySelector('[data-role="compare-list"]'),
    leftPanel: document.querySelector('[data-side-panel="left"]'),
    rightPanel: document.querySelector('[data-side-panel="right"]'),
    leftPanelToggles: [...document.querySelectorAll('[data-command="left-panel-toggle"]')],
    rightPanelToggles: [
      ...document.querySelectorAll(
        '[data-command="right-panel-toggle"], [data-command="comments-toggle"]'
      ),
    ],
    resourceTabs: [...document.querySelectorAll("[data-resource-tab]")],
    resourcePanels: [...document.querySelectorAll("[data-resource-panel]")],
    stateList: document.querySelector('[data-role="state-list"]'),
    assetList: document.querySelector('[data-role="asset-list"]'),
    outputList: document.querySelector('[data-role="output-list"]'),
    bottomDock: document.querySelector('[data-role="bottom-dock"]'),
    composer: document.querySelector(".rf-composer"),
    composerTitle: document.querySelector('[data-role="composer-title"]'),
    composerTarget: document.querySelector('[data-role="composer-target"]'),
    composerInput: document.querySelector('[data-role="composer-input"]'),
    composerSeverities: [...document.querySelectorAll(".rf-severity[data-severity]")],
    floatingGuide: document.querySelector(".rf-floating-guide"),
    floatingGuideTitle: document.querySelector('[data-role="floating-guide-title"]'),
    floatingGuideCopy: document.querySelector('[data-role="floating-guide-copy"]'),
    toast: document.querySelector(".rf-toast"),
  };

  function currentStage() {
    return stages.find((stage) => stage.id === state.stageId) || stages[0] || {
      id: "unknown",
      title: "未登记关卡",
      summary: "",
      confirm: "",
    };
  }

  function stageArtboards(stageId = state.stageId) {
    return artboards.filter((item) => item.stageId === stageId);
  }

  function uniqueBy(items, key) {
    const seen = new Set();
    return items.filter((item) => {
      const value = item[key];
      if (seen.has(value)) return false;
      seen.add(value);
      return true;
    });
  }

  function stagePages(stageId = state.stageId) {
    return uniqueBy(stageArtboards(stageId), "pageId").map((item) => ({
      id: item.pageId,
      title: item.pageTitle,
      summary: item.pageSummary || item.summary,
      count: stageArtboards(stageId).filter((candidate) => candidate.pageId === item.pageId).length,
    }));
  }

  function stageVariants(stageId = state.stageId) {
    return uniqueBy(stageArtboards(stageId), "variantId").map((item) => ({
      id: item.variantId,
      title: item.variantTitle,
      summary: item.variantSummary || "",
      count: stageArtboards(stageId).filter((candidate) => candidate.variantId === item.variantId).length,
    }));
  }

  function visibleArtboards() {
    if (state.mode === "compare") {
      const selected = new Set(state.compareIds);
      return stageArtboards().filter((item) => selected.has(item.id));
    }
    return stageArtboards().filter((item) => (
      (state.pageId === "all" || item.pageId === state.pageId)
      && (state.variantId === "all" || item.variantId === state.variantId)
    ));
  }

  function getArtboardNode(artboardId) {
    return els.pageNodes.find((node) => node.dataset.reviewArtboard === artboardId) || null;
  }

  function getModuleNode(artboardId, moduleId) {
    return getArtboardNode(artboardId)
      ?.querySelector(`[data-review-module="${CSS.escape(moduleId)}"]`) || null;
  }

  function currentModuleList() {
    return visibleArtboards().flatMap((artboard) =>
      artboard.modules.map((module) => ({
        ...module,
        artboardId: artboard.id,
        stageId: artboard.stageId,
        pageId: artboard.pageId,
        pageTitle: artboard.pageTitle,
        variantId: artboard.variantId,
        variantTitle: artboard.variantTitle,
      }))
    );
  }

  function showToast(message) {
    if (!els.toast) return;
    els.toast.textContent = message;
    els.toast.dataset.open = "true";
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
      els.toast.dataset.open = "false";
    }, 2200);
  }

  function stageStatus(stage) {
    return state.workflow.stages?.[stage.id]?.status || stage.status || "idle";
  }

  function canOpenStage(stageId) {
    const targetIndex = stages.findIndex((stage) => stage.id === stageId);
    if (targetIndex < 0) return false;
    return stages.slice(0, targetIndex).every((stage) => stageStatus(stage) === "done");
  }

  function renderStageNav() {
    if (!els.stageList) return;
    els.stageList.style.gridTemplateColumns =
      `repeat(${Math.max(stages.length, 1)}, minmax(64px, 1fr))`;
    els.stageList.replaceChildren(...stages.map((stage, index) => {
      const button = document.createElement("button");
      const status = stage.id === state.stageId ? "active" : stageStatus(stage);
      button.type = "button";
      button.className = "rf-stage";
      button.dataset.stageTarget = stage.id;
      button.dataset.state = status;
      button.disabled = !canOpenStage(stage.id);
      button.setAttribute("aria-current", String(stage.id === state.stageId));
      button.innerHTML = `
        <span class="rf-stage-number">${index + 1}</span>
        <strong>${stage.title}</strong>
        <span>${stage.summary || stage.confirm}</span>`;
      return button;
    }));
  }

  function renderPageList() {
    if (!els.pageList) return;
    const pages = stagePages();
    const total = stageArtboards().length;
    const items = [{
      id: "all",
      title: "全部页面",
      summary: "先看页面关系",
      count: total,
      icon: "全",
    }, ...pages.map((page, index) => ({
      ...page,
      icon: String(index + 1),
    }))];

    els.pageList.replaceChildren(...items.map((page) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "rf-page-item";
      button.dataset.pageTarget = page.id;
      button.setAttribute("aria-current", String(state.pageId === page.id));
      button.innerHTML = `
        <span class="rf-page-icon">${page.icon}</span>
        <span class="rf-page-copy"><strong>${page.title}</strong><span>${page.summary || "查看这一页"}</span></span>
        <span class="rf-page-count">${page.count}</span>`;
      item.appendChild(button);
      return item;
    }));
  }

  function makeResourceItem(glyph, title, copy, meta = "", href = "") {
    const item = document.createElement(href ? "a" : "div");
    item.className = "rf-resource-item";
    if (href) {
      item.classList.add("rf-resource-link");
      item.href = href;
    }
    const icon = document.createElement("span");
    icon.className = "rf-resource-glyph";
    icon.textContent = glyph;
    const text = document.createElement("span");
    text.className = "rf-resource-copy";
    const strong = document.createElement("strong");
    const description = document.createElement("span");
    strong.textContent = title;
    description.textContent = copy;
    text.append(strong, description);
    const detail = document.createElement("span");
    detail.className = "rf-resource-meta";
    detail.textContent = meta;
    item.append(icon, text, detail);
    return item;
  }

  function renderResourcePanels() {
    els.resourceTabs.forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.resourceTab === state.resourceTab));
    });
    els.resourcePanels.forEach((panel) => {
      panel.hidden = panel.dataset.resourcePanel !== state.resourceTab;
    });

    if (els.stateList) {
      const states = Array.isArray(state.contract?.states) ? state.contract.states : [];
      const visibleStates = states.slice(0, 8);
      els.stateList.replaceChildren(...(
        visibleStates.length
          ? visibleStates.map((item, index) => makeResourceItem(
            item.id || `S${index + 1}`,
            item.title || "未命名状态",
            item.finalRequired === false ? "辅助状态" : "最终设计必须覆盖",
            index === 0 ? `${states.length} 项` : ""
          ))
          : [
            makeResourceItem("默", "默认状态", "当前画板的初始表现", "1"),
            makeResourceItem("交", "交互状态", "操作后由原型实时切换", "可点"),
            makeResourceItem("边", "边界状态", "由阶段契约登记并校验", "待载入"),
          ]
      ));
    }

    if (els.assetList) {
      const tokens = {
        ...(state.contract?.tokens || {}),
        ...(state.contract?.meta?.tokens || {}),
      };
      const tokenKeys = Object.keys(tokens);
      const tokenCount = (needle) => tokenKeys.filter((key) => key.includes(needle)).length;
      els.assetList.replaceChildren(
        makeResourceItem("色", "颜色", "品牌色、状态色和画布色", tokenCount("color") || "默认"),
        makeResourceItem("字", "字体", "字号、字重和行高", tokenCount("font") || "默认"),
        makeResourceItem("距", "间距", "页面、组件和内容节奏", tokenCount("space") || "默认"),
        makeResourceItem("角", "圆角", "控件、面板和状态标记", tokenCount("radius") || "默认")
      );
    }

    if (els.outputList) {
      els.outputList.replaceChildren(
        makeResourceItem("原", "网页原型", "当前可交互设计事实源", "HTML", "./index.html"),
        makeResourceItem("契", "阶段契约", "需求、页面、旅程、动作和状态", "JSON", "./index.design.json"),
        makeResourceItem("评", "评审记录", "评论、处理状态与方案决策", "本地保存"),
        makeResourceItem("规", "设计规格", "由已批准原型导出给开发", "待交付")
      );
    }
  }

  function setResourceTab(tab) {
    if (!els.resourceTabs.some((button) => button.dataset.resourceTab === tab)) return;
    state.resourceTab = tab;
    renderResourcePanels();
  }

  function updatePanelState() {
    root.dataset.leftPanel = state.leftPanelOpen ? "open" : "closed";
    root.dataset.rightPanel = state.rightPanelOpen ? "open" : "closed";
    els.leftPanel?.toggleAttribute("data-open", state.leftPanelOpen);
    els.rightPanel?.toggleAttribute("data-open", state.rightPanelOpen);
    els.leftPanelToggles.forEach((button) => {
      button.setAttribute("aria-pressed", String(state.leftPanelOpen));
    });
    els.rightPanelToggles.forEach((button) => {
      button.setAttribute("aria-pressed", String(state.rightPanelOpen));
    });
    window.requestAnimationFrame(() => fitBoard());
  }

  function compactWorkspace() {
    return window.matchMedia("(max-width: 1100px)").matches;
  }

  function togglePanel(side) {
    if (side === "left") {
      state.leftPanelOpen = !state.leftPanelOpen;
      if (
        state.leftPanelOpen
        && compactWorkspace()
        && workspace.narrowPanelPolicy === "exclusive"
      ) state.rightPanelOpen = false;
    }
    if (side === "right") {
      state.rightPanelOpen = !state.rightPanelOpen;
      if (
        state.rightPanelOpen
        && compactWorkspace()
        && workspace.narrowPanelPolicy === "exclusive"
      ) state.leftPanelOpen = false;
    }
    updatePanelState();
  }

  function makeStripTab(target, type, current) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "rf-page-tab";
    button.dataset[`${type}Target`] = target.id;
    button.setAttribute("aria-current", String(current === target.id));
    button.innerHTML = `
      <span class="rf-page-thumb" aria-hidden="true"></span>
      <span><strong>${target.title}</strong><span>${target.summary || `${target.count} 张画板`}</span></span>`;
    return button;
  }

  function renderStrip() {
    if (!els.strip) return;
    const variants = stageVariants();
    const pages = stagePages();
    const compareVariants = variants.length > 1;
    const label = document.createElement("div");
    label.className = "rf-strip-copy";
    label.innerHTML = compareVariants
      ? "<strong>方案一眼看全</strong><span>选页面后可横向对比同一页面</span>"
      : "<strong>页面一眼看全</strong><span>点击后在画板单独查看</span>";

    const targets = compareVariants
      ? [{ id: "all", title: "全部方案", summary: "并列比较", count: stageArtboards().length }, ...variants]
      : pages;
    const type = compareVariants ? "variant" : "page";
    const current = compareVariants ? state.variantId : state.pageId;
    els.strip.replaceChildren(label, ...targets.map((target) => makeStripTab(target, type, current)));
    els.strip.dataset.kind = compareVariants ? "variants" : "pages";
  }

  function renderVariantDecision() {
    if (!els.variantDecision) return;
    const variants = stageVariants();
    const show = variants.length > 1;
    els.variantDecision.hidden = !show;
    if (!show) return;

    const selected = state.workflow.selections?.[state.stageId] || {};
    const current = variants.find((variant) => variant.id === state.variantId);
    if (els.variantDecisionTitle) {
      els.variantDecisionTitle.textContent = current
        ? `当前查看：${current.title}`
        : "当前查看：全部方案";
    }
    if (els.variantDecisionState) {
      const selectedVariant = variants.find((variant) => variant.id === selected.variantId);
      els.variantDecisionState.textContent = selectedVariant
        ? `已选方向：${selectedVariant.title}`
        : "尚未选定主方向";
    }
    if (els.variantNote && document.activeElement !== els.variantNote) {
      els.variantNote.value = selected.note || "";
    }
    if (els.variantSelect) {
      els.variantSelect.disabled = !current;
      els.variantSelect.textContent = current ? `选择“${current.title}”` : "先单独查看一个方案";
    }
  }

  function ensureCompareSelection() {
    const candidates = stageArtboards();
    const validIds = new Set(candidates.map((item) => item.id));
    state.compareIds = state.compareIds.filter((id) => validIds.has(id));
    if (state.compareIds.length < 2) {
      state.compareIds = candidates.slice(0, 4).map((item) => item.id);
    }
  }

  function renderComparePanel() {
    if (!els.compareList) return;
    const selected = new Set(state.compareIds);
    const candidates = stageArtboards();
    els.compareList.replaceChildren(...candidates.map((artboard, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "rf-compare-item";
      button.dataset.compareArtboard = artboard.id;
      button.setAttribute("aria-pressed", String(selected.has(artboard.id)));
      button.innerHTML = `
        <span class="rf-compare-check" aria-hidden="true">${selected.has(artboard.id) ? "✓" : ""}</span>
        <span class="rf-compare-copy">
          <strong>${artboard.pageTitle}</strong>
          <span>${artboard.variantTitle}${candidates.length > 1 ? ` · 画板 ${index + 1}` : ""}</span>
        </span>`;
      return button;
    }));
  }

  function renderGuideIndex() {
    if (!els.guideIndex) return;
    const modules = currentModuleList();
    if (!modules.length) {
      els.guideIndex.innerHTML = '<p class="rf-panel-copy">当前没有可讲解的模块。</p>';
      return;
    }
    els.guideIndex.replaceChildren(...modules.map((module, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "rf-guide-index-item";
      button.dataset.guideArtboard = module.artboardId;
      button.dataset.guideModule = module.id;
      button.setAttribute(
        "aria-current",
        String(state.activeModuleKey === `${module.artboardId}:${module.id}`)
      );
      button.innerHTML = `
        <span>${index + 1}</span>
        <strong>${module.title}</strong>
        <small>${module.pageTitle}</small>`;
      return button;
    }));
  }

  function updateModeHint() {
    if (!els.canvasModeHint) return;
    const copy = {
      experience: {
        title: "体验原型",
        text: "直接点击页面；双指或拖动空白处移动画布。",
      },
      explain: {
        title: "查看讲解",
        text: "蓝色编号是可讲解模块；点击画面或右侧清单查看说明。",
      },
      comment: {
        title: "添加评论",
        text: "单击或拖动添加评论；双指平移，空格拖动画布。",
      },
      compare: {
        title: "并排对比",
        text: "从右侧选择 2 至 4 张画板，画布会自动并排适应。",
      },
    }[state.mode];
    els.canvasModeHint.dataset.mode = state.mode;
    if (els.canvasModeTitle) els.canvasModeTitle.textContent = copy.title;
    if (els.canvasModeCopy) els.canvasModeCopy.textContent = copy.text;
  }

  function updateWorkspaceCopy() {
    const stage = currentStage();
    const page = stagePages().find((item) => item.id === state.pageId);
    const variant = stageVariants().find((item) => item.id === state.variantId);
    const visible = visibleArtboards();

    if (els.projectTitle) els.projectTitle.textContent = project.title || "未命名产品";
    if (els.projectMeta) els.projectMeta.textContent = project.subtitle || "设计全过程工作台";
    if (els.locationStage) els.locationStage.textContent = stage.title;
    if (els.locationVersion) els.locationVersion.textContent = `版本 ${project.version || "草稿"}`;
    if (els.pageSectionTitle) els.pageSectionTitle.textContent = `${stage.title} · 项目内容`;
    if (els.leftNote) {
      els.leftNote.innerHTML = `<strong>本关要确认</strong><span>${stage.confirm}</span>`;
    }
    if (els.canvasTitle) {
      els.canvasTitle.textContent = [
        page?.title || "全部页面",
        variant?.title,
      ].filter(Boolean).join(" · ");
    }
    if (els.canvasSubtitle) {
      els.canvasSubtitle.textContent = visible.length
        ? `${visible.length} 张画板；左侧按页面筛选，底部按${stageVariants().length > 1 ? "方案" : "页面"}切换`
        : "当前筛选没有画板内容";
    }
    if (els.footerTitle) els.footerTitle.textContent = `当前：${stage.title}`;
    if (els.footerCopy) els.footerCopy.textContent = stage.confirm;
    if (els.confirmButton) {
      const stageIndex = stages.findIndex((item) => item.id === stage.id);
      const isLast = stageIndex === stages.length - 1;
      const next = stages[stageIndex + 1];
      const waiting = stageStatus(stage) === "done" && next && !stageArtboards(next.id).length;
      const delivered = isLast && stageStatus(stage) === "done";
      els.confirmButton.disabled = Boolean(waiting || delivered);
      if (delivered) {
        els.confirmButton.textContent = "设计交付已批准";
      } else if (stage.id === "visual-final" && state.contract?.phase === "direction") {
        els.confirmButton.textContent = "确认方向，继续全量设计";
      } else {
        els.confirmButton.textContent = waiting
          ? `${stage.title}已确认，等待${next.title}`
          : isLast
            ? "确认设计交付"
            : `确认${stage.title}，进入下一关`;
      }
    }
  }

  function renderWorkspaceNavigation() {
    renderStageNav();
    renderPageList();
    renderResourcePanels();
    renderStrip();
    renderVariantDecision();
    renderComparePanel();
    renderGuideIndex();
    updateModeHint();
    updateWorkspaceCopy();
  }

  function applyArtboardFilter() {
    const visible = visibleArtboards();
    const visibleIds = new Set(visible.map((item) => item.id));
    els.pageNodes.forEach((node) => {
      const visible = visibleIds.has(node.dataset.reviewArtboard);
      node.dataset.workspaceVisible = String(visible);
      node.dataset.active = String(visible);
      node.removeAttribute("data-compare-index");
    });
    if (state.mode === "compare") {
      visible.forEach((artboard, index) => {
        const node = getArtboardNode(artboard.id);
        if (node) node.dataset.compareIndex = String.fromCharCode(65 + index);
      });
    }
    root.dataset.view = visibleIds.size <= 1 ? "single" : "all";
    window.requestAnimationFrame(() => fitBoard());
  }

  function clearModuleSelection() {
    document.querySelectorAll("[data-review-selected]").forEach((node) => {
      node.removeAttribute("data-review-selected");
    });
    state.activeModuleKey = null;
    state.tourIndex = -1;
  }

  function refreshWorkspace(options = {}) {
    if (!options.keepModule) {
      clearModuleSelection();
      renderGuideEmpty();
      hideFloatingGuide();
    }
    renderWorkspaceNavigation();
    applyArtboardFilter();
    if (state.mode === "explain") addModuleTags();
    else removeModuleTags();
  }

  function setStage(stageId) {
    if (!stages.some((stage) => stage.id === stageId)) return;
    if (!canOpenStage(stageId)) {
      showToast("请先确认前面的关卡。");
      return;
    }
    state.stageId = stageId;
    const stage = currentStage();
    state.pageId = stage.defaultPageId;
    state.variantId = stage.defaultVariantId;
    state.compareIds = [];
    state.workflow.activeStageId = stageId;
    refreshWorkspace();
  }

  function setPage(pageId, options = {}) {
    if (pageId !== "all" && !stagePages().some((page) => page.id === pageId)) return;
    state.pageId = pageId;
    if (state.mode === "compare") {
      state.compareIds = stageArtboards()
        .filter((artboard) => pageId === "all" || artboard.pageId === pageId)
        .slice(0, 4)
        .map((artboard) => artboard.id);
    }
    refreshWorkspace(options);
  }

  function setVariant(variantId, options = {}) {
    if (variantId !== "all" && !stageVariants().some((variant) => variant.id === variantId)) return;
    state.variantId = variantId;
    if (state.mode === "compare") {
      state.compareIds = stageArtboards()
        .filter((artboard) => variantId === "all" || artboard.variantId === variantId)
        .slice(0, 4)
        .map((artboard) => artboard.id);
    }
    refreshWorkspace(options);
  }

  function setMode(mode, options = {}) {
    if (!["experience", "explain", "comment", "compare"].includes(mode)) return;
    state.mode = mode;
    if (options.openPanel !== false) {
      state.rightPanelOpen = true;
      if (compactWorkspace() && workspace.narrowPanelPolicy === "exclusive") {
        state.leftPanelOpen = false;
      }
      updatePanelState();
    }
    if (mode === "compare") ensureCompareSelection();
    root.dataset.mode = mode;
    els.modes.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
    });
    hideComposer();
    hideFloatingGuide();
    clearDraft();
    renderWorkspaceNavigation();
    applyArtboardFilter();

    if (mode === "explain") {
      addModuleTags();
      if (!state.activeModuleKey) renderGuideEmpty();
      renderGuideIndex();
      updateModeHint();
      showToast("讲解模式：点击任意高亮模块查看完整说明。");
      return;
    }
    removeModuleTags();
    clearModuleSelection();
    if (mode === "comment") {
      renderComments();
      showToast("评论模式：单击放评论钉，拖动可框选区域。");
    } else if (mode === "compare") {
      showToast("对比模式：从右侧选择 2 至 4 张画板并排查看。");
    } else {
      showToast("体验模式：现在可以按真实原型逻辑操作。");
    }
    updateModeHint();
  }

  function boardNaturalSize() {
    const visiblePages = els.pageNodes.filter((node) => node.dataset.workspaceVisible === "true");
    const gap = 34;
    const width = visiblePages.reduce((sum, node) => sum + node.offsetWidth, 0)
      + Math.max(0, visiblePages.length - 1) * gap;
    const height = Math.max(...visiblePages.map((node) => node.offsetHeight), 1);
    return { width: Math.max(width, 1), height };
  }

  function applyTransform() {
    board.style.transform =
      `translate(calc(-50% + ${state.panX}px), calc(-50% + ${state.panY}px)) scale(${state.scale})`;
    root.dataset.panX = String(Math.round(state.panX));
    root.dataset.panY = String(Math.round(state.panY));
    if (els.zoomLabel) els.zoomLabel.textContent = `${Math.round(state.scale * 100)}%`;
    updateModuleTagScale();
  }

  function fitBoard() {
    const natural = boardNaturalSize();
    const availableWidth = Math.max(100, canvas.clientWidth - 76);
    const dockHeight = els.bottomDock?.offsetHeight || 0;
    const availableHeight = Math.max(100, canvas.clientHeight - Math.max(78, dockHeight + 30));
    state.scale = Math.min(1, availableWidth / natural.width, availableHeight / natural.height);
    state.panX = 0;
    state.panY = 0;
    applyTransform();
  }

  function zoomBy(delta) {
    state.scale = Math.min(1.5, Math.max(0.2, state.scale + delta));
    applyTransform();
  }

  function resetBoard() {
    state.scale = 1;
    state.panX = 0;
    state.panY = 0;
    applyTransform();
  }

  function setPanEnabled(enabled) {
    state.panEnabled = enabled;
    updatePanState();
  }

  function updatePanState(dragging = state.draggingBoard) {
    const handActive = state.panEnabled || state.spacePan;
    root.dataset.handTool = String(handActive);
    root.dataset.panning = String(dragging);
    if (els.panButton) {
      els.panButton.setAttribute("aria-pressed", String(state.panEnabled));
      els.panButton.textContent = "手形";
      els.panButton.title = "空白处可直接拖动；启用后可从页面上拖动";
    }
    canvas.style.cursor = dragging ? "grabbing" : handActive ? "grab" : "";
  }

  function canStartPan(event) {
    if (event.button === 1) return true;
    if (event.button !== 0) return false;
    if (state.panEnabled || state.spacePan) return true;
    if (state.mode === "comment") return false;
    return event.target === canvas || event.target === board;
  }

  function startBoardPan(event) {
    state.draggingBoard = true;
    state.suppressCanvasClick = false;
    state.boardPointer = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      panX: state.panX,
      panY: state.panY,
      moved: false,
    };
    canvas.setPointerCapture(event.pointerId);
    updatePanState(true);
    event.preventDefault();
  }

  function finishBoardPan(event) {
    if (!state.draggingBoard || state.boardPointer?.id !== event.pointerId) return;
    state.suppressCanvasClick = Boolean(state.boardPointer.moved);
    if (state.suppressCanvasClick) {
      window.setTimeout(() => {
        state.suppressCanvasClick = false;
      }, 0);
    }
    state.draggingBoard = false;
    state.boardPointer = null;
    updatePanState(false);
  }

  function addModuleTags() {
    removeModuleTags();
    currentModuleList().forEach((module, index) => {
      const node = getModuleNode(module.artboardId, module.id);
      if (!node) return;
      if (getComputedStyle(node).position === "static") node.style.position = "relative";
      const tag = document.createElement("span");
      tag.className = "rf-module-tag";
      tag.innerHTML = `<b>${index + 1}</b><span>${module.title}</span>`;
      tag.dataset.moduleTag = `${module.artboardId}:${module.id}`;
      tag.style.top = "6px";
      tag.style.left = "6px";
      node.appendChild(tag);
    });
    updateModuleTagScale();
  }

  function updateModuleTagScale() {
    const inverse = 1 / Math.max(state.scale, 0.2);
    document.querySelectorAll(".rf-module-tag").forEach((tag) => {
      tag.style.transform = `scale(${inverse})`;
      tag.style.transformOrigin = "top left";
    });
  }

  function removeModuleTags() {
    document.querySelectorAll(".rf-module-tag").forEach((node) => node.remove());
  }

  function renderGuideEmpty() {
    if (els.guideKicker) els.guideKicker.textContent = "原型讲解";
    if (els.guideTitle) els.guideTitle.textContent = "选择一个模块";
    if (els.guideProgress) els.guideProgress.style.width = "0%";
    if (els.guideFacts) {
      els.guideFacts.innerHTML = `
        <p class="rf-panel-copy">
          点击画板里的大模块查看说明，或从头开始讲解。每个模块都会说明它是什么、为什么这样放、
          能做什么、有哪些状态，以及这一轮需要确认什么。
        </p>`;
    }
    renderGuideIndex();
  }

  function fact(label, value) {
    const wrapper = document.createElement("div");
    wrapper.className = "rf-guide-fact";
    const title = document.createElement("strong");
    const copy = document.createElement("span");
    title.textContent = label;
    copy.textContent = value || "本轮没有额外说明。";
    wrapper.append(title, copy);
    return wrapper;
  }

  function positionFloatingGuide(node, module) {
    if (!els.floatingGuide || !node) return;
    const rect = node.getBoundingClientRect();
    const width = 290;
    const left = Math.min(window.innerWidth - width - 16, Math.max(16, rect.right + 12));
    const top = Math.min(window.innerHeight - 150, Math.max(70, rect.top));
    els.floatingGuide.style.left = `${left}px`;
    els.floatingGuide.style.top = `${top}px`;
    els.floatingGuideTitle.textContent = module.title;
    els.floatingGuideCopy.textContent = module.what;
    els.floatingGuide.hidden = false;
  }

  function hideFloatingGuide() {
    if (els.floatingGuide) els.floatingGuide.hidden = true;
  }

  function selectModule(artboardId, moduleId, options = {}) {
    const artboard = artboardMap.get(artboardId);
    const module = artboard?.modules.find((item) => item.id === moduleId);
    if (!artboard || !module) return;

    state.stageId = artboard.stageId;
    state.pageId = artboard.pageId;
    state.variantId = artboard.variantId;
    refreshWorkspace({ keepModule: true });
    clearModuleSelection();

    const list = currentModuleList();
    state.activeModuleKey = `${artboardId}:${moduleId}`;
    state.tourIndex = list.findIndex(
      (item) => item.artboardId === artboardId && item.id === moduleId
    );

    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      const node = getModuleNode(artboardId, moduleId);
      if (!node) return;
      node.dataset.reviewSelected = "true";
      if (els.guideKicker) {
        els.guideKicker.textContent =
          `${artboard.pageTitle} · ${artboard.variantTitle} · 模块 ${state.tourIndex + 1}/${list.length}`;
      }
      if (els.guideTitle) els.guideTitle.textContent = module.title;
      if (els.guideProgress) {
        els.guideProgress.style.width = `${((state.tourIndex + 1) / list.length) * 100}%`;
      }
      if (els.guideFacts) {
        els.guideFacts.replaceChildren(
          fact("这是什么", module.what),
          fact("为什么这样放", module.why),
          fact("用户可以做什么", module.actions),
          fact("状态与边界", module.states),
          fact("这一轮要确认什么", module.confirm)
        );
      }
      if (!options.silentPopover) positionFloatingGuide(node, module);
      renderGuideIndex();
    }));
  }

  function stepGuide(direction) {
    const list = currentModuleList();
    if (!list.length) return;
    let next = state.tourIndex;
    if (next < 0) next = direction > 0 ? 0 : list.length - 1;
    else next = (next + direction + list.length) % list.length;
    const module = list[next];
    selectModule(module.artboardId, module.id);
  }

  function showHotspots() {
    const nodes = visibleArtboards()
      .map((artboard) => getArtboardNode(artboard.id))
      .filter(Boolean);
    const hotspots = nodes.flatMap((node) => [...node.querySelectorAll("[data-prototype-action]")]);
    if (!hotspots.length) {
      showToast("当前画板没有登记可操作位置。");
      return;
    }
    hotspots.forEach((node) => {
      if (getComputedStyle(node).position === "static") node.style.position = "relative";
      const hint = document.createElement("span");
      hint.className = "rf-hotspot-hint";
      node.appendChild(hint);
      window.setTimeout(() => hint.remove(), 1900);
    });
    showToast(`已显示 ${hotspots.length} 个可操作位置。`);
  }

  function performPrototypeAction(node) {
    const action = node.dataset.prototypeAction || "";
    if (action.startsWith("page:")) {
      setPage(action.slice(5));
      return;
    }
    if (action.startsWith("state:")) {
      const artboard = node.closest("[data-review-artboard]");
      if (artboard) {
        artboard.dataset.prototypeState = action.slice(6);
        showToast(`页面状态已切换为：${action.slice(6)}`);
      }
      return;
    }
    if (action.startsWith("toggle:")) {
      const selector = action.slice(7);
      const target = document.querySelector(selector);
      if (target) target.toggleAttribute("data-open");
      return;
    }
    if (action.startsWith("tab:")) {
      const [, group, value] = action.split(":");
      const scope = node.closest("[data-review-artboard]") || document;
      if (!group || !value) return;
      scope.querySelectorAll(`[data-prototype-tab-group="${group}"]`).forEach((tab) => {
        const active = tab.dataset.prototypeAction === action;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
      });
      scope.querySelectorAll(`[data-prototype-panel-group="${group}"]`).forEach((panel) => {
        panel.hidden = panel.dataset.prototypePanel !== value;
      });
      return;
    }
    showToast(node.dataset.prototypeHint || "已触发该原型交互。");
  }

  function localComments() {
    try {
      return JSON.parse(window.localStorage.getItem(storageKey) || "[]");
    } catch {
      return [];
    }
  }

  function saveLocalComments(comments) {
    window.localStorage.setItem(storageKey, JSON.stringify(comments));
  }

  function localWorkflow() {
    try {
      return JSON.parse(window.localStorage.getItem(workflowStorageKey) || "{}");
    } catch {
      return {};
    }
  }

  async function loadWorkflow() {
    let stored = null;
    try {
      const response = await fetch("/api/workflow", { cache: "no-store" });
      if (!response.ok) throw new Error("API unavailable");
      stored = await response.json();
    } catch {
      stored = localWorkflow();
    }
    state.workflow = {
      ...state.workflow,
      ...(stored || {}),
      stages: { ...state.workflow.stages, ...(stored?.stages || {}) },
      selections: { ...state.workflow.selections, ...(stored?.selections || {}) },
    };
    const resumable = state.workflow.activeStageId;
    if (resumable && canOpenStage(resumable)) state.stageId = resumable;
    refreshWorkspace();
  }

  async function loadContract() {
    try {
      const response = await fetch("/index.design.json", { cache: "no-store" });
      if (!response.ok) return;
      const contract = await response.json();
      if (contract?.schema === "design-stage-contract/v1") {
        state.contract = contract;
      }
    } catch {
      state.contract = null;
    }
  }

  async function saveWorkflow() {
    state.workflow.projectId = project.id || "prototype";
    state.workflow.activeStageId = state.stageId;
    state.workflow.updatedAt = new Date().toISOString();
    try {
      const response = await fetch("/api/workflow", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state.workflow),
      });
      if (!response.ok) throw new Error("API unavailable");
      state.workflow = await response.json();
    } catch {
      window.localStorage.setItem(workflowStorageKey, JSON.stringify(state.workflow));
    }
    renderWorkspaceNavigation();
  }

  async function loadComments() {
    try {
      const response = await fetch("/api/comments", { cache: "no-store" });
      if (!response.ok) throw new Error("API unavailable");
      const payload = await response.json();
      state.comments = Array.isArray(payload.comments) ? payload.comments : [];
    } catch {
      state.comments = localComments();
    }
    renderComments();
  }

  async function createComment(comment) {
    let stored = null;
    try {
      const response = await fetch("/api/comments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(comment),
      });
      if (!response.ok) throw new Error("API unavailable");
      stored = await response.json();
    } catch {
      stored = { ...comment, id: comment.id || `local-${Date.now()}` };
      state.comments.push(stored);
      saveLocalComments(state.comments);
    }
    if (!state.comments.some((item) => item.id === stored.id)) state.comments.push(stored);
    renderComments();
    return stored;
  }

  async function updateComment(id, patch) {
    const index = state.comments.findIndex((item) => item.id === id);
    if (index < 0) return;
    let updated = { ...state.comments[index], ...patch, updatedAt: new Date().toISOString() };
    try {
      const response = await fetch(`/api/comments/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!response.ok) throw new Error("API unavailable");
      updated = await response.json();
    } catch {
      saveLocalComments(state.comments.map((item) => (item.id === id ? updated : item)));
    }
    state.comments[index] = updated;
    renderComments();
  }

  function artboardForComment(comment) {
    return artboardMap.get(comment.artboardId)
      || artboards.find((item) => (
        item.stageId === comment.stageId
        && item.pageId === comment.pageId
        && (!comment.variantId || item.variantId === comment.variantId)
      ))
      || artboards.find((item) => item.pageId === comment.pageId);
  }

  function commentLabel(comment) {
    const artboard = artboardForComment(comment);
    const module = artboard?.modules.find((item) => item.id === comment.moduleId);
    const base = artboard
      ? `${artboard.pageTitle}${stageVariants(artboard.stageId).length > 1 ? ` · ${artboard.variantTitle}` : ""}`
      : comment.pageId;
    return `${base}${module ? ` · ${module.title}` : " · 自选区域"}`;
  }

  function renderCommentOverlays() {
    document.querySelectorAll(".rf-comment-pin, .rf-comment-region").forEach((node) => node.remove());
    state.comments.forEach((comment, index) => {
      const artboard = artboardForComment(comment);
      const page = artboard ? getArtboardNode(artboard.id) : null;
      if (!page || !comment.anchor) return;
      const marker = document.createElement("button");
      marker.type = "button";
      marker.dataset.commentId = comment.id;
      marker.dataset.status = comment.status || "open";
      marker.title = comment.text;
      marker.setAttribute("aria-label", `评论 ${index + 1}：${comment.text}`);

      if (comment.anchor.type === "region") {
        marker.className = "rf-comment-region";
        marker.dataset.index = String(index + 1);
        marker.style.left = `${comment.anchor.x * 100}%`;
        marker.style.top = `${comment.anchor.y * 100}%`;
        marker.style.width = `${comment.anchor.w * 100}%`;
        marker.style.height = `${comment.anchor.h * 100}%`;
      } else {
        marker.className = "rf-comment-pin";
        marker.textContent = String(index + 1);
        marker.style.left = `${comment.anchor.x * 100}%`;
        marker.style.top = `${comment.anchor.y * 100}%`;
      }
      page.appendChild(marker);
    });
  }

  function filteredComments() {
    const stageComments = state.comments.filter((comment) => comment.stageId === state.stageId);
    if (state.commentFilter === "all") return stageComments;
    return stageComments.filter(
      (comment) => (comment.status || "open") === state.commentFilter
    );
  }

  function renderComments() {
    renderCommentOverlays();
    if (els.commentCount) {
      const openCount = state.comments.filter(
        (comment) => (comment.status || "open") !== "resolved"
      ).length;
      els.commentCount.textContent = String(openCount);
    }
    if (!els.commentList) return;
    const comments = filteredComments();
    if (!comments.length) {
      els.commentList.innerHTML = `
        <li class="rf-empty">
          当前关卡还没有${state.commentFilter === "resolved" ? "已解决" : "待处理"}意见。
          进入评论模式后，单击放评论钉，拖动可框选区域。
        </li>`;
      return;
    }

    els.commentList.replaceChildren(...comments.map((comment) => {
      const item = document.createElement("li");
      item.className = "rf-comment-item";
      item.dataset.commentId = comment.id;
      item.dataset.status = comment.status || "open";
      item.dataset.active = String(comment.id === state.activeCommentId);

      const meta = document.createElement("div");
      meta.className = "rf-comment-meta";
      const target = document.createElement("span");
      const severity = document.createElement("span");
      target.textContent = commentLabel(comment);
      severity.textContent = {
        question: "疑问",
        suggestion: "建议",
        must: "必须修改",
      }[comment.severity] || "建议";
      meta.append(target, severity);

      const copy = document.createElement("p");
      copy.textContent = comment.text;
      const reply = comment.reply ? document.createElement("div") : null;
      if (reply) {
        reply.className = "rf-comment-reply";
        const replyTitle = document.createElement("strong");
        const replyCopy = document.createElement("span");
        replyTitle.textContent = "处理说明";
        replyCopy.textContent = comment.reply;
        reply.append(replyTitle, replyCopy);
      }
      const statusRow = document.createElement("div");
      statusRow.className = "rf-status-row";
      const statusButton = document.createElement("button");
      statusButton.type = "button";
      statusButton.className = "rf-comment-status";
      statusButton.dataset.commentStatus = comment.id;
      statusButton.dataset.active = String((comment.status || "open") === "resolved");
      statusButton.textContent = {
        open: "开始处理",
        processing: "标记解决",
        resolved: "重新打开",
      }[comment.status || "open"];
      statusRow.append(statusButton);

      item.append(meta, copy);
      if (reply) item.append(reply);
      item.append(statusRow);
      return item;
    }));
  }

  function focusComment(comment) {
    const artboard = artboardForComment(comment);
    if (!artboard) return;
    state.activeCommentId = comment.id;
    state.stageId = artboard.stageId;
    state.pageId = artboard.pageId;
    state.variantId = artboard.variantId;
    refreshWorkspace({ keepModule: true });
    window.requestAnimationFrame(() => {
      renderComments();
      const marker = document.querySelector(`[data-comment-id="${CSS.escape(comment.id)}"]`);
      marker?.animate(
        [
          { boxShadow: "0 0 0 0 rgba(157,70,59,.5)" },
          { boxShadow: "0 0 0 12px rgba(157,70,59,0)" },
        ],
        { duration: 900, iterations: 2 }
      );
    });
  }

  function clearDraft() {
    document.querySelectorAll(".rf-comment-draft").forEach((node) => node.remove());
    state.drawing = null;
  }

  function findPageAt(clientX, clientY) {
    return document.elementsFromPoint(clientX, clientY)
      .find((node) => node.matches?.("[data-review-artboard]")) || null;
  }

  function findModuleAt(clientX, clientY, pageNode) {
    return document.elementsFromPoint(clientX, clientY)
      .find((node) => node.matches?.("[data-review-module]") && pageNode.contains(node)) || null;
  }

  function normalizedPoint(page, clientX, clientY) {
    const rect = page.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (clientY - rect.top) / rect.height)),
    };
  }

  function beginCommentDraw(event) {
    if (state.mode !== "comment" || event.button !== 0) return;
    if (event.target.closest(".rf-comment-pin, .rf-comment-region")) return;
    const page = findPageAt(event.clientX, event.clientY);
    if (!page) return;
    const moduleNode = findModuleAt(event.clientX, event.clientY, page);
    const start = normalizedPoint(page, event.clientX, event.clientY);
    const draft = document.createElement("div");
    draft.className = "rf-comment-draft";
    draft.style.left = `${start.x * 100}%`;
    draft.style.top = `${start.y * 100}%`;
    draft.style.width = "0";
    draft.style.height = "0";
    page.appendChild(draft);
    state.drawing = {
      pointerId: event.pointerId,
      page,
      artboardId: page.dataset.reviewArtboard,
      pageId: page.dataset.reviewPage,
      variantId: page.dataset.reviewVariant,
      moduleId: moduleNode?.dataset.reviewModule || null,
      start,
      current: start,
      draft,
      clientStart: { x: event.clientX, y: event.clientY },
    };
    canvas.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function moveCommentDraw(event) {
    const drawing = state.drawing;
    if (!drawing || drawing.pointerId !== event.pointerId) return;
    const current = normalizedPoint(drawing.page, event.clientX, event.clientY);
    drawing.current = current;
    const left = Math.min(drawing.start.x, current.x);
    const top = Math.min(drawing.start.y, current.y);
    const width = Math.abs(current.x - drawing.start.x);
    const height = Math.abs(current.y - drawing.start.y);
    Object.assign(drawing.draft.style, {
      left: `${left * 100}%`,
      top: `${top * 100}%`,
      width: `${width * 100}%`,
      height: `${height * 100}%`,
    });
  }

  function endCommentDraw(event) {
    const drawing = state.drawing;
    if (!drawing || drawing.pointerId !== event.pointerId) return;
    const moved = Math.hypot(
      event.clientX - drawing.clientStart.x,
      event.clientY - drawing.clientStart.y
    );
    const left = Math.min(drawing.start.x, drawing.current.x);
    const top = Math.min(drawing.start.y, drawing.current.y);
    const width = Math.abs(drawing.current.x - drawing.start.x);
    const height = Math.abs(drawing.current.y - drawing.start.y);

    state.pendingComment = {
      artboardId: drawing.artboardId,
      pageId: drawing.pageId,
      variantId: drawing.variantId,
      moduleId: drawing.moduleId,
      anchor: moved < 8
        ? { type: "pin", x: drawing.start.x, y: drawing.start.y }
        : { type: "region", x: left, y: top, w: width, h: height },
      prototypeState: drawing.page.dataset.prototypeState || "default",
    };
    drawing.draft.remove();
    state.drawing = null;
    openComposer(event.clientX, event.clientY);
  }

  function openComposer(clientX, clientY) {
    if (!els.composer || !state.pendingComment) return;
    const artboard = artboardMap.get(state.pendingComment.artboardId);
    const module = artboard?.modules.find((item) => item.id === state.pendingComment.moduleId);
    els.composerTitle.textContent =
      state.pendingComment.anchor.type === "region" ? "评论这个区域" : "评论这个位置";
    els.composerTarget.textContent = `${artboard?.pageTitle || state.pendingComment.pageId}`
      + `${artboard && stageVariants(artboard.stageId).length > 1 ? ` · ${artboard.variantTitle}` : ""}`
      + `${module ? ` · ${module.title}` : " · 自选区域"}`;
    els.composerInput.value = "";
    els.composerSeverities.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.severity === "suggestion"));
    });
    const width = 300;
    const left = Math.min(window.innerWidth - width - 12, Math.max(12, clientX + 14));
    const top = Math.min(window.innerHeight - 260, Math.max(70, clientY + 14));
    els.composer.style.left = `${left}px`;
    els.composer.style.top = `${top}px`;
    els.composer.hidden = false;
    els.composerInput.focus();
  }

  function hideComposer() {
    if (els.composer) els.composer.hidden = true;
    state.pendingComment = null;
  }

  async function savePendingComment() {
    if (!state.pendingComment) return;
    const text = els.composerInput.value.trim();
    if (!text) {
      showToast("请先写下意见。");
      els.composerInput.focus();
      return;
    }
    const severity =
      els.composerSeverities.find((button) => button.getAttribute("aria-pressed") === "true")
        ?.dataset.severity || "suggestion";
    const stage = currentStage();
    const comment = {
      id: crypto.randomUUID ? crypto.randomUUID() : `comment-${Date.now()}`,
      projectId: project.id || "prototype",
      projectTitle: project.title || document.title,
      stageId: stage.id,
      stageTitle: stage.title,
      artboardId: state.pendingComment.artboardId,
      pageId: state.pendingComment.pageId,
      variantId: state.pendingComment.variantId,
      moduleId: state.pendingComment.moduleId,
      anchor: state.pendingComment.anchor,
      prototypeState: state.pendingComment.prototypeState,
      version: project.version || "draft",
      severity,
      status: "open",
      text,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    const stored = await createComment(comment);
    hideComposer();
    state.activeCommentId = stored.id;
    renderComments();
    showToast("意见已记录，并绑定到当前关卡、方案和区域。");
  }

  function exportComments() {
    const payload = {
      schema: "design-review-comments/v1",
      project,
      workflow: state.workflow,
      exportedAt: new Date().toISOString(),
      comments: state.comments,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `review-comments-${project.id || "prototype"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function selectCurrentVariant() {
    const variant = stageVariants().find((item) => item.id === state.variantId);
    if (!variant) {
      showToast("请先从底部单独打开一个方案。");
      return;
    }
    state.workflow.selections[state.stageId] = {
      ...(state.workflow.selections[state.stageId] || {}),
      variantId: variant.id,
      note: els.variantNote?.value.trim() || "",
      updatedAt: new Date().toISOString(),
    };
    await saveWorkflow();
    showToast(`已选择“${variant.title}”，补充意见也已保存。`);
  }

  async function saveVariantNote() {
    if (!els.variantNote) return;
    state.workflow.selections[state.stageId] = {
      ...(state.workflow.selections[state.stageId] || {}),
      note: els.variantNote.value.trim(),
      updatedAt: new Date().toISOString(),
    };
    await saveWorkflow();
    showToast("补充与融合意见已保存。");
  }

  function toggleCompareArtboard(artboardId) {
    const selected = new Set(state.compareIds);
    if (selected.has(artboardId)) {
      selected.delete(artboardId);
    } else if (selected.size >= 4) {
      showToast("一次最多对比 4 张画板。");
      return;
    } else {
      selected.add(artboardId);
    }
    state.compareIds = [...selected];
    refreshWorkspace();
  }

  function selectAllCompare() {
    state.compareIds = stageArtboards().slice(0, 4).map((artboard) => artboard.id);
    refreshWorkspace();
  }

  function clearCompare() {
    state.compareIds = [];
    renderComparePanel();
    applyArtboardFilter();
    updateWorkspaceCopy();
  }

  async function confirmStage() {
    const stage = currentStage();
    const blocking = state.comments.filter((comment) => (
      comment.stageId === stage.id
      && comment.severity === "must"
      && (comment.status || "open") !== "resolved"
    ));
    if (blocking.length) {
      setMode("comment");
      state.commentFilter = "open";
      renderComments();
      showToast(`还有 ${blocking.length} 条“必须修改”未解决，暂不能进入下一关。`);
      return;
    }
    if (!stageArtboards().length) {
      showToast("当前关卡还没有画板内容，不能确认。");
      return;
    }
    if (stage.id === "visual-final" && state.contract?.phase === "direction") {
      const selected = state.workflow.selections?.[stage.id]?.variantId;
      if (!selected) {
        showToast("先单独查看并选择一个高保真方向。");
        return;
      }
      state.workflow.stages[stage.id] = {
        status: "active",
        checkpoint: "direction-approved",
        directionApprovedAt: new Date().toISOString(),
      };
      await saveWorkflow();
      refreshWorkspace();
      showToast("主方向已记录；请展开全部页面和状态后再确认视觉定稿。");
      return;
    }

    state.workflow.stages[stage.id] = {
      status: "done",
      confirmedAt: new Date().toISOString(),
    };
    const index = stages.findIndex((item) => item.id === stage.id);
    const next = stages[index + 1];
    if (next) {
      if (!stageArtboards(next.id).length) {
        state.workflow.awaitingStageId = next.id;
        await saveWorkflow();
        refreshWorkspace();
        showToast(`已记录${stage.title}确认；${next.title}内容生成后再开放。`);
        return;
      }
      state.workflow.stages[next.id] = {
        ...(state.workflow.stages[next.id] || {}),
        status: "active",
      };
      state.stageId = next.id;
      state.pageId = next.defaultPageId;
      state.variantId = next.defaultVariantId;
    }
    await saveWorkflow();
    refreshWorkspace();
    showToast(next ? `已确认${stage.title}，进入${next.title}。` : "全部设计关卡已确认。");
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const modeButton = event.target.closest(".rf-mode[data-mode]");
      if (modeButton) {
        setMode(modeButton.dataset.mode);
        return;
      }

      const stageButton = event.target.closest("[data-stage-target]");
      if (stageButton) {
        setStage(stageButton.dataset.stageTarget);
        return;
      }

      const pageButton = event.target.closest("[data-page-target]");
      if (pageButton) {
        setPage(pageButton.dataset.pageTarget);
        return;
      }

      const variantButton = event.target.closest("[data-variant-target]");
      if (variantButton) {
        setVariant(variantButton.dataset.variantTarget);
        return;
      }

      const compareButton = event.target.closest("[data-compare-artboard]");
      if (compareButton) {
        toggleCompareArtboard(compareButton.dataset.compareArtboard);
        return;
      }

      const guideButton = event.target.closest("[data-guide-artboard][data-guide-module]");
      if (guideButton) {
        selectModule(guideButton.dataset.guideArtboard, guideButton.dataset.guideModule);
        return;
      }

      const resourceTab = event.target.closest("[data-resource-tab]");
      if (resourceTab) {
        setResourceTab(resourceTab.dataset.resourceTab);
        return;
      }

      const commandButton = event.target.closest("[data-command]");
      if (commandButton) {
        const command = commandButton.dataset.command;
        if (command === "zoom-in") zoomBy(0.1);
        if (command === "zoom-out") zoomBy(-0.1);
        if (command === "fit") fitBoard();
        if (command === "reset") resetBoard();
        if (command === "pan") setPanEnabled(!state.panEnabled);
        if (command === "hotspots") showHotspots();
        if (command === "guide-start") stepGuide(1);
        if (command === "guide-prev") stepGuide(-1);
        if (command === "guide-next") stepGuide(1);
        if (command === "comment-save") savePendingComment();
        if (command === "comment-cancel") hideComposer();
        if (command === "comments-export") exportComments();
        if (command === "comments-toggle") setMode("comment");
        if (command === "left-panel-toggle") togglePanel("left");
        if (command === "right-panel-toggle") togglePanel("right");
        if (command === "variant-select") selectCurrentVariant();
        if (command === "variant-note-save") saveVariantNote();
        if (command === "compare-all") selectAllCompare();
        if (command === "compare-clear") clearCompare();
        if (command === "stage-confirm") confirmStage();
        event.stopPropagation();
        return;
      }

      const moduleNode = event.target.closest("[data-review-module]");
      if (moduleNode && state.mode === "explain") {
        const artboardNode = moduleNode.closest("[data-review-artboard]");
        selectModule(artboardNode.dataset.reviewArtboard, moduleNode.dataset.reviewModule);
        event.preventDefault();
        event.stopPropagation();
        return;
      }

      const actionNode = event.target.closest("[data-prototype-action]");
      if (actionNode && state.mode === "experience") {
        performPrototypeAction(actionNode);
        event.preventDefault();
        return;
      }

      const marker = event.target.closest("[data-comment-id]");
      if (marker) {
        const comment = state.comments.find((item) => item.id === marker.dataset.commentId);
        if (comment) focusComment(comment);
        event.preventDefault();
        event.stopPropagation();
        return;
      }

      const item = event.target.closest(".rf-comment-item");
      if (item && !event.target.closest("[data-comment-status]")) {
        const comment = state.comments.find((entry) => entry.id === item.dataset.commentId);
        if (comment) focusComment(comment);
      }

      const statusButton = event.target.closest("[data-comment-status]");
      if (statusButton) {
        const comment = state.comments.find((entry) => entry.id === statusButton.dataset.commentStatus);
        if (comment) {
          const nextStatus = {
            open: "processing",
            processing: "resolved",
            resolved: "open",
          }[comment.status || "open"];
          updateComment(comment.id, { status: nextStatus });
        }
      }

      const filterButton = event.target.closest(".rf-comment-filter[data-filter]");
      if (filterButton) {
        state.commentFilter = filterButton.dataset.filter;
        document.querySelectorAll(".rf-comment-filter[data-filter]").forEach((itemNode) => {
          itemNode.setAttribute("aria-pressed", String(itemNode === filterButton));
        });
        renderComments();
      }
    });

    els.composerSeverities.forEach((button) => {
      button.addEventListener("click", () => {
        els.composerSeverities.forEach((item) => item.setAttribute("aria-pressed", "false"));
        button.setAttribute("aria-pressed", "true");
      });
    });

    canvas.addEventListener("click", (event) => {
      if (state.suppressCanvasClick) {
        state.suppressCanvasClick = false;
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (state.mode === "experience" && event.target === canvas) showHotspots();
    });

    canvas.addEventListener("pointerdown", (event) => {
      if (canStartPan(event)) {
        startBoardPan(event);
        return;
      }
      if (state.mode === "comment") {
        beginCommentDraw(event);
      }
    });

    canvas.addEventListener("pointermove", (event) => {
      if (state.draggingBoard && state.boardPointer?.id === event.pointerId) {
        const dx = event.clientX - state.boardPointer.x;
        const dy = event.clientY - state.boardPointer.y;
        if (Math.hypot(dx, dy) > 3) state.boardPointer.moved = true;
        state.panX = state.boardPointer.panX + dx;
        state.panY = state.boardPointer.panY + dy;
        applyTransform();
        return;
      }
      if (state.mode === "comment") {
        moveCommentDraw(event);
      }
    });

    canvas.addEventListener("pointerup", (event) => {
      if (state.draggingBoard) {
        finishBoardPan(event);
        return;
      }
      if (state.mode === "comment") {
        endCommentDraw(event);
      }
    });

    canvas.addEventListener("pointercancel", (event) => {
      if (state.draggingBoard) finishBoardPan(event);
      else if (state.mode === "comment") clearDraft();
    });

    canvas.addEventListener("wheel", (event) => {
      event.preventDefault();
      if (event.ctrlKey || event.metaKey) {
        zoomBy(event.deltaY > 0 ? -0.06 : 0.06);
        return;
      }
      const unit = event.deltaMode === 1
        ? 16
        : event.deltaMode === 2
          ? canvas.clientHeight
          : 1;
      const horizontal = event.deltaX || (event.shiftKey ? event.deltaY : 0);
      const vertical = event.shiftKey ? 0 : event.deltaY;
      state.panX -= horizontal * unit;
      state.panY -= vertical * unit;
      applyTransform();
    }, { passive: false });

    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hideComposer();
        hideFloatingGuide();
        state.leftPanelOpen = false;
        state.rightPanelOpen = false;
        updatePanelState();
        setMode("experience", { openPanel: false });
        return;
      }
      if (event.target instanceof Element && event.target.matches("textarea, input, select")) return;
      if (event.code === "Space") {
        if (!state.spacePan) {
          state.spacePan = true;
          updatePanState();
        }
        event.preventDefault();
        return;
      }
      if (event.key.toLowerCase() === "c") setMode("comment");
      if (event.key.toLowerCase() === "g") setMode("explain");
      if (event.key.toLowerCase() === "e") setMode("experience");
      if (event.key.toLowerCase() === "x") setMode("compare");
    });

    window.addEventListener("keyup", (event) => {
      if (event.code !== "Space") return;
      state.spacePan = false;
      updatePanState();
    });

    window.addEventListener("blur", () => {
      state.spacePan = false;
      if (state.draggingBoard) {
        state.draggingBoard = false;
        state.boardPointer = null;
      }
      updatePanState(false);
    });

    window.addEventListener("resize", () => {
      if (
        compactWorkspace()
        && workspace.narrowPanelPolicy === "exclusive"
        && state.leftPanelOpen
        && state.rightPanelOpen
      ) {
        state.leftPanelOpen = false;
        updatePanelState();
        return;
      }
      fitBoard();
    });
  }

  function init() {
    root.dataset.mode = state.mode;
    root.dataset.workspaceLayout = workspace.layout;
    if (els.projectTitle) els.projectTitle.textContent = project.title || "未命名产品";
    bindEvents();
    updatePanState();
    updatePanelState();
    renderGuideEmpty();
    refreshWorkspace();
    Promise.all([loadComments(), loadWorkflow(), loadContract()]).then(() => {
      renderComments();
      refreshWorkspace();
    });
  }

  init();
})();
