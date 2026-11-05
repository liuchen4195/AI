"use strict";

const messagesEl = document.getElementById("messages");
const welcomeEl = document.getElementById("welcome");
const composerEl = document.getElementById("composer");
const inputEl = document.getElementById("question-input");
const sendButton = document.getElementById("send-button");
const clearButton = document.getElementById("clear-button");
const inputErrorEl = document.getElementById("input-error");
const traceContentEl = document.getElementById("trace-content");

const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

const state = {
    isProcessing: false,
    isComposing: false,
    traceView: { kind: "empty" },
};

const STATUS_LABELS = {
    success: { text: "成功", symbol: "✓", className: "success" },
    partial: { text: "部分成功", symbol: "!", className: "partial" },
    failed: { text: "失败", symbol: "×", className: "failed" },
    running: { text: "处理中", symbol: "…", className: "running" },
};

const TOOL_STATUS_LABELS = {
    success: { text: "成功", symbol: "✓", className: "success" },
    error: { text: "失败", symbol: "×", className: "error" },
    rejected: { text: "未执行", symbol: "–", className: "rejected" },
    running: { text: "执行中", symbol: "…", className: "running" },
    unknown: { text: "状态未知", symbol: "?", className: "unknown" },
};

const EXECUTION_MODE_LABELS = {
    none: "未调用工具",
    serial: "串行调用",
    parallel: "并行调用",
    mixed: "混合调用",
};

const ROUND_MODE_LABELS = {
    single: "单工具调用",
    parallel: "并行调用",
};

const CALL_EXECUTION_LABELS = {
    serial: "串行",
    parallel: "并行",
};

const STOP_REASON_LABELS = {
    completed: "正常完成",
    model_request_failed: "模型请求失败",
    empty_answer: "模型未返回回答",
    max_model_rounds: "达到最大模型轮次",
    max_tool_rounds: "达到最大工具轮次",
    tool_call_limit: "达到工具调用上限",
    city_limit: "达到城市数量上限",
    internal_error: "内部错误",
};

const ERROR_TYPE_LABELS = {
    tool_not_found: "工具不存在",
    argument_parse_failed: "参数解析失败",
    validation_failed: "参数校验失败",
    timeout: "调用超时",
    tool_execution_failed: "工具执行失败",
    tool_reported_error: "工具返回错误",
    model_request_failed: "模型请求失败",
    empty_answer: "模型未返回回答",
    max_model_rounds: "达到最大模型轮次",
    internal_error: "内部错误",
};

const FAILURE_STAGE_LABELS = {
    model_request: "模型请求",
    final_answer: "最终回答",
    model_loop: "模型循环",
    internal: "内部处理",
};

function makeSpinner() {
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    spinner.setAttribute("aria-hidden", "true");
    return spinner;
}

function renderTraceState(kind, title, detail) {
    traceContentEl.replaceChildren();

    const box = document.createElement("div");
    box.className = `trace-state trace-${kind}`;

    const heading = document.createElement("div");
    heading.className = "trace-state-heading";
    if (kind === "processing") {
        heading.append(makeSpinner());
    }

    const titleEl = document.createElement("p");
    titleEl.className = "trace-state-title";
    titleEl.textContent = title;
    heading.append(titleEl);

    const detailEl = document.createElement("p");
    detailEl.className = "trace-state-detail";
    detailEl.textContent = detail;

    box.append(heading, detailEl);
    traceContentEl.append(box);
}

function createElement(tagName, className = "", text = undefined) {
    const element = document.createElement(tagName);
    if (className) {
        element.className = className;
    }
    if (text !== undefined) {
        element.textContent = text;
    }
    return element;
}

function asNumber(value) {
    if (value === null || value === undefined || value === "") {
        return null;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function formatDateTime(value) {
    if (!value) {
        return "未记录";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return "未记录";
    }
    const pad = (part, length = 2) => String(part).padStart(length, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
        + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.`
        + `${pad(date.getMilliseconds(), 3)}`;
}

function formatDuration(value) {
    const milliseconds = asNumber(value);
    if (milliseconds === null) {
        return "未记录";
    }
    if (milliseconds < 1000) {
        return `${milliseconds} ms`;
    }
    return `${(milliseconds / 1000).toFixed(2)} s（${milliseconds} ms）`;
}

function formatCount(value, unit) {
    const count = asNumber(value);
    return count === null ? "未记录" : `${count} ${unit}`;
}

function formatPayload(value, emptyText) {
    if (value === null || value === undefined) {
        return emptyText;
    }
    if (typeof value === "string") {
        return value.length ? value : emptyText;
    }
    if (typeof value === "number" || typeof value === "boolean") {
        return String(value);
    }
    try {
        return JSON.stringify(value, null, 2);
    } catch (error) {
        return String(value);
    }
}

function normalizeTokens(tokens) {
    const data = tokens || {};
    const input = asNumber(data.input);
    const output = asNumber(data.output);
    const total = asNumber(data.total);
    const hasAny = input !== null || output !== null || total !== null;
    const label = (value) => (
        value === null ? "未返回" : value.toLocaleString("zh-CN")
    );

    return {
        input: label(input),
        output: label(output),
        total: label(total),
        partial: data.complete !== true && hasAny,
    };
}

function createStat(label, value) {
    const item = createElement("div", "stat");
    item.append(
        createElement("dt", "", label),
        createElement("dd", "", value)
    );
    return item;
}

function buildStatusBadge(status) {
    const info = STATUS_LABELS[status] || {
        text: status || "未知",
        symbol: "?",
        className: "unknown",
    };
    const badge = createElement("span", `trace-status trace-status-${info.className}`);
    badge.setAttribute("role", "status");

    const symbol = createElement("span", "trace-status-symbol", info.symbol);
    symbol.setAttribute("aria-hidden", "true");
    badge.append(symbol, createElement("span", "trace-status-text", info.text));
    return badge;
}

function buildToolStatus(status) {
    const info = TOOL_STATUS_LABELS[status] || TOOL_STATUS_LABELS.unknown;
    const badge = createElement("span", `tool-status tool-status-${info.className}`);
    const symbol = createElement("span", "tool-status-symbol", info.symbol);
    symbol.setAttribute("aria-hidden", "true");
    badge.append(symbol, createElement("span", "tool-status-text", info.text));
    return badge;
}

function buildRoundBadge(mode) {
    const label = ROUND_MODE_LABELS[mode] || "未记录";
    const className = mode === "parallel"
        ? "parallel"
        : (mode === "single" ? "single" : "unknown");
    return createElement("span", `round-badge round-badge-${className}`, label);
}

function buildFailureBlock(error) {
    const data = error || {};
    const block = createElement("div", "trace-failure");
    block.setAttribute("role", "alert");

    const stage = data.stage
        ? (FAILURE_STAGE_LABELS[data.stage] || data.stage)
        : "未记录";
    const round = asNumber(data.round);
    const title = data.stage
        ? `失败阶段：${stage}${round !== null ? `（第 ${round} 次）` : ""}`
        : "失败阶段：未记录";

    block.append(createElement("p", "trace-failure-title", title));

    if (data.type) {
        block.append(createElement(
            "p",
            "trace-failure-type",
            `错误类型：${ERROR_TYPE_LABELS[data.type] || data.type}`
        ));
    }

    block.append(createElement(
        "p",
        "trace-failure-message",
        data.message || "本轮未能生成最终回答。"
    ));
    return block;
}

function buildTraceOverview(trace) {
    const section = createElement("section", "trace-overview");

    const head = createElement("div", "trace-overview-head");
    const question = createElement("div", "trace-question");
    question.append(
        createElement("p", "trace-question-label", "本轮问题"),
        createElement("p", "trace-question-text", trace.question || "未记录")
    );
    head.append(question, buildStatusBadge(trace.status));
    section.append(head);

    if (trace.status === "failed") {
        section.append(buildFailureBlock(trace.error));
    }

    const tokens = normalizeTokens(trace.tokens);
    const stats = createElement("dl", "stat-grid");
    stats.append(
        createStat("模型请求", formatCount(trace.model_requests, "次")),
        createStat("工具调用", formatCount(trace.tool_calls, "次")),
        createStat("工具轮次", formatCount(trace.tool_rounds, "轮")),
        createStat("调用方式", EXECUTION_MODE_LABELS[trace.execution_mode] || "未记录"),
        createStat("开始时间", formatDateTime(trace.started_at)),
        createStat("结束时间", formatDateTime(trace.finished_at)),
        createStat("总耗时", formatDuration(trace.duration_ms)),
        createStat("输入 Token", tokens.input),
        createStat("输出 Token", tokens.output),
        createStat("总 Token", tokens.total),
        createStat(
            "停止原因",
            STOP_REASON_LABELS[trace.stop_reason] || trace.stop_reason || "未记录"
        )
    );
    section.append(stats);

    if (tokens.partial) {
        section.append(createElement(
            "p",
            "token-note",
            "部分模型请求未返回 Token 用量，以上为已返回部分的累计值。"
        ));
    }

    return section;
}

function buildMetaItem(label, value, mono = false) {
    const item = createElement("div", "tool-meta-item");
    item.append(
        createElement("dt", "", label),
        createElement("dd", mono ? "mono" : "", value)
    );
    return item;
}

function buildDetail(summaryText, contentText) {
    const details = createElement("details", "tool-detail");
    details.append(
        createElement("summary", "", summaryText),
        createElement("pre", "", contentText)
    );
    return details;
}

function normalizeToolStatus(call) {
    if (call && TOOL_STATUS_LABELS[call.status]) {
        return call.status;
    }
    if (call && call.error_type) {
        return "error";
    }
    return "unknown";
}

function buildToolCall(call, roundNumber, roundMode) {
    call = call || {};
    const status = normalizeToolStatus(call);
    const article = createElement("article", `tool-call tool-call-${status}`);

    const head = createElement("div", "tool-call-head");
    const titleBlock = createElement("div", "tool-call-title-block");
    titleBlock.append(
        createElement("p", "tool-call-name", call.name || "未记录"),
        createElement(
            "p",
            "tool-call-description",
            call.description || "未提供用途说明"
        )
    );
    head.append(titleBlock, buildToolStatus(status));
    article.append(head);

    const executionLabel = CALL_EXECUTION_LABELS[call.execution]
        || (roundMode === "parallel"
            ? "并行"
            : (roundMode === "single" ? "串行" : "未记录"));

    const meta = createElement("dl", "tool-meta");
    meta.append(
        buildMetaItem("调用编号", call.call_id || "未记录", true),
        buildMetaItem("所属轮次", `第 ${roundNumber} 轮`),
        buildMetaItem("执行方式", executionLabel),
        buildMetaItem("开始时间", formatDateTime(call.started_at)),
        buildMetaItem("结束时间", formatDateTime(call.finished_at)),
        buildMetaItem(
            "调用耗时",
            status === "running" ? "执行中" : formatDuration(call.duration_ms)
        )
    );
    article.append(meta);

    if (call.error_type || status === "error") {
        const errorBlock = createElement("div", "tool-error");
        const typeLabel = ERROR_TYPE_LABELS[call.error_type]
            || call.error_type
            || "未记录";
        errorBlock.append(
            createElement("p", "tool-error-title", `错误类型：${typeLabel}`),
            createElement(
                "p",
                "tool-error-message",
                call.error_message || "未提供错误信息。"
            )
        );
        article.append(errorBlock);
    }

    const details = createElement("div", "tool-details");
    details.append(
        buildDetail("调用参数", formatPayload(call.arguments, "未记录")),
        buildDetail(
            "返回结果",
            formatPayload(
                call.result,
                status === "running" ? "执行中，尚未返回结果。" : "无结果。"
            )
        )
    );
    article.append(details);
    return article;
}

function buildToolRound(round, index) {
    round = round || {};
    const calls = Array.isArray(round.calls) ? round.calls : [];
    const roundNumber = asNumber(round.round) ?? index + 1;
    const callCount = asNumber(round.call_count) ?? calls.length;
    const mode = round.mode;
    const modeLabel = ROUND_MODE_LABELS[mode] || "未记录";

    const container = createElement("section", "tool-round");
    const head = createElement("div", "tool-round-head");
    const titleBlock = createElement("div", "tool-round-title-block");
    titleBlock.append(
        createElement("p", "tool-round-title", `第 ${roundNumber} 轮`),
        createElement(
            "p",
            "tool-round-meta",
            `${callCount} 个工具 · ${modeLabel} · 轮次耗时 ${formatDuration(round.duration_ms)}`
        )
    );
    head.append(titleBlock, buildRoundBadge(mode));
    container.append(head);

    if (mode === "parallel" && callCount > 1) {
        container.append(createElement(
            "p",
            "round-note",
            "同一轮调用按模型返回顺序展示，不代表完成顺序；完成先后以结束时间为准。"
        ));
    }

    const callsEl = createElement("div", "tool-calls");
    if (calls.length) {
        calls.forEach((call) => {
            callsEl.append(buildToolCall(call, roundNumber, mode));
        });
    } else {
        callsEl.append(createElement("p", "tool-round-empty", "该轮未记录工具调用详情。"));
    }
    container.append(callsEl);
    return container;
}

function buildToolRounds(trace) {
    const section = createElement("section", "tool-rounds");
    section.append(createElement("h3", "trace-section-title", "调用过程"));

    const rounds = Array.isArray(trace.rounds) ? trace.rounds : [];
    if (!rounds.length) {
        const toolCallCount = asNumber(trace.tool_calls);
        const hasCalls = toolCallCount !== null && toolCallCount > 0;
        const empty = createElement("div", "trace-empty-tools");
        empty.append(
            createElement(
                "p",
                "trace-empty-tools-title",
                hasCalls ? "工具调用详情未记录" : "本轮未调用工具"
            ),
            createElement(
                "p",
                "trace-empty-tools-detail",
                hasCalls
                    ? "本轮记录到工具调用次数，但没有可展示的轮次详情。"
                    : "本轮模型直接给出了回答，没有发起工具调用。"
            )
        );
        section.append(empty);
        return section;
    }

    rounds.forEach((round, index) => {
        section.append(buildToolRound(round, index));
    });
    return section;
}

function renderTrace(trace) {
    traceContentEl.replaceChildren();
    if (!trace) {
        renderTraceState("failed", "本轮失败", "未获取到本轮轨迹。");
        return;
    }
    traceContentEl.append(
        buildTraceOverview(trace),
        buildToolRounds(trace)
    );
}

function renderTraceView() {
    const view = state.traceView;

    if (view.kind === "empty") {
        renderTraceState(
            "empty",
            "等待用户提问",
            "提交问题后，这里会展示模型请求和工具调用过程。"
        );
        return;
    }

    if (view.kind === "processing") {
        renderTraceState(
            "processing",
            "本轮正在执行…",
            "正在请求模型并调用工具，请稍候。"
        );
        return;
    }

    if (view.kind === "failed") {
        renderTraceState(
            "failed",
            view.title || "本轮失败",
            view.detail || "未获取到本轮轨迹。"
        );
        return;
    }

    if (view.kind === "trace") {
        renderTrace(view.trace);
    }
}

function setTraceView(view) {
    state.traceView = view;
    renderTraceView();
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        messagesEl.scrollTop = messagesEl.scrollHeight;

        const lastMessage = messagesEl.lastElementChild;
        if (lastMessage) {
            lastMessage.scrollIntoView({
                behavior: reducedMotionQuery.matches ? "auto" : "smooth",
                block: "nearest",
            });
        }
    });
}

function autoResizeInput() {
    inputEl.style.height = "auto";
    inputEl.style.height = `${Math.min(inputEl.scrollHeight, 160)}px`;
}

function showInputError(message) {
    inputErrorEl.textContent = message;
    inputErrorEl.hidden = false;
    inputEl.setAttribute("aria-invalid", "true");
    inputEl.focus();
}

function clearInputError() {
    inputErrorEl.textContent = "";
    inputErrorEl.hidden = true;
    inputEl.removeAttribute("aria-invalid");
}

function appendMessage(role, text, { isError = false, isWaiting = false } = {}) {
    const wrapper = document.createElement("article");
    const classes = ["message", `message-${role}`];
    if (isError) {
        classes.push("message-error");
    }
    if (isWaiting) {
        classes.push("message-waiting");
    }
    wrapper.className = classes.join(" ");

    const roleEl = document.createElement("p");
    roleEl.className = "message-role";
    roleEl.textContent = role === "user" ? "你" : "助手";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    if (isWaiting) {
        bubble.append(makeSpinner());
        const waitingLabel = document.createElement("span");
        waitingLabel.textContent = "正在思考…";
        bubble.append(waitingLabel);
        wrapper.setAttribute("aria-label", "助手正在思考");
    } else {
        bubble.textContent = text ?? "";
        if (isError) {
            bubble.setAttribute("role", "alert");
        }
    }

    wrapper.append(roleEl, bubble);
    messagesEl.append(wrapper);

    if (welcomeEl) {
        welcomeEl.hidden = true;
    }

    scrollToBottom();
    return { wrapper, bubble };
}

function appendWaitingMessage() {
    return appendMessage("assistant", "", { isWaiting: true });
}

function replaceWaiting(waiting, text, isError) {
    waiting.wrapper.classList.remove("message-waiting");
    waiting.wrapper.classList.toggle("message-error", Boolean(isError));
    waiting.wrapper.removeAttribute("aria-label");

    waiting.bubble.replaceChildren();
    waiting.bubble.textContent = text || (isError ? "请求失败，请稍后重试。" : "");

    if (isError) {
        waiting.bubble.setAttribute("role", "alert");
    } else {
        waiting.bubble.removeAttribute("role");
    }

    scrollToBottom();
}

function setProcessing(processing) {
    state.isProcessing = processing;

    inputEl.disabled = processing;
    sendButton.disabled = processing;
    clearButton.disabled = processing;
    sendButton.textContent = processing ? "处理中…" : "发送";

    messagesEl.setAttribute("aria-busy", String(processing));
    traceContentEl.setAttribute("aria-busy", String(processing));

    if (!processing) {
        inputEl.focus();
        autoResizeInput();
    }
}

function restoreDraft(text) {
    inputEl.value = text;
    autoResizeInput();
}

async function readJson(response) {
    try {
        return await response.json();
    } catch (error) {
        return null;
    }
}

function getApiError(data, fallback) {
    if (data && data.error && typeof data.error.message === "string") {
        return data.error.message;
    }
    if (
        data
        && data.trace
        && data.trace.error
        && typeof data.trace.error.message === "string"
    ) {
        return data.trace.error.message;
    }
    return fallback;
}

async function sendQuestion() {
    if (state.isProcessing) {
        return;
    }

    const raw = inputEl.value;
    const question = raw.trim();
    if (!question) {
        showInputError("请输入要查询的问题");
        return;
    }

    clearInputError();

    // 输入错误会在提交前被本地拦截；这里保存上一轮轨迹，供服务端 400 时恢复
    const previousTraceView = state.traceView;

    appendMessage("user", question);
    inputEl.value = "";
    autoResizeInput();

    const waiting = appendWaitingMessage();
    setTraceView({ kind: "processing" });
    setProcessing(true);

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
        });
        const data = await readJson(response);

        if (response.status === 400) {
            // 输入在执行前被拒绝：保留上一轮轨迹
            setTraceView(previousTraceView);
            replaceWaiting(waiting, getApiError(data, "请输入要查询的问题"), true);
            restoreDraft(raw);
            return;
        }

        if (response.status === 409) {
            setTraceView({
                kind: "failed",
                title: "本轮失败",
                detail: "上一次请求尚未结束，本轮未执行。",
            });
            replaceWaiting(waiting, getApiError(data, "正在处理中，请稍后重试。"), true);
            restoreDraft(raw);
            return;
        }

        if (!response.ok) {
            setTraceView({
                kind: "failed",
                title: "本轮失败",
                detail: "未获取到本轮轨迹。",
            });
            replaceWaiting(
                waiting,
                getApiError(data, `请求失败（HTTP ${response.status}）。`),
                true
            );
            restoreDraft(raw);
            return;
        }

        if (data && data.ok) {
            const answer = typeof data.answer === "string" && data.answer.trim()
                ? data.answer
                : "（助手未返回文本回答）";
            replaceWaiting(waiting, answer, false);
            setTraceView({ kind: "trace", trace: data.trace });
            return;
        }

        // 200 + ok:false：本轮已执行但未得到最终回答
        setTraceView({
            kind: "trace",
            trace: data && data.trace ? data.trace : { status: "failed" },
        });
        replaceWaiting(
            waiting,
            getApiError(data, "本轮未能生成回答，请稍后重试。"),
            true
        );
        restoreDraft(raw);
    } catch (error) {
        setTraceView({
            kind: "failed",
            title: "本轮失败",
            detail: "未获取到本轮轨迹。",
        });
        replaceWaiting(waiting, "网络请求失败，请检查服务是否运行。", true);
        restoreDraft(raw);
    } finally {
        setProcessing(false);
        scrollToBottom();
    }
}

function resetConversationUI() {
    [...messagesEl.children].forEach((child) => {
        if (child !== welcomeEl) {
            child.remove();
        }
    });

    if (welcomeEl) {
        welcomeEl.hidden = false;
    }

    inputEl.value = "";
    clearInputError();
    autoResizeInput();
    setTraceView({ kind: "empty" });
    messagesEl.scrollTop = 0;
    inputEl.focus();
}

async function clearConversation() {
    if (state.isProcessing) {
        return;
    }

    if (!window.confirm("确定清空当前对话和本轮轨迹吗？")) {
        return;
    }

    clearButton.disabled = true;
    try {
        const response = await fetch("/api/clear", { method: "POST" });
        const data = await readJson(response);

        if (!response.ok || !data || data.ok !== true) {
            showInputError(`清空失败：${getApiError(data, "请稍后重试。")}`);
            return;
        }

        resetConversationUI();
    } catch (error) {
        showInputError("清空失败：网络请求异常，请稍后重试。");
    } finally {
        clearButton.disabled = state.isProcessing;
    }
}

composerEl.addEventListener("submit", (event) => {
    event.preventDefault();
    sendQuestion();
});

inputEl.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey) {
        return;
    }
    if (state.isComposing || event.isComposing || event.keyCode === 229) {
        return;
    }
    event.preventDefault();
    sendQuestion();
});

inputEl.addEventListener("input", () => {
    clearInputError();
    autoResizeInput();
});

inputEl.addEventListener("compositionstart", () => {
    state.isComposing = true;
});

inputEl.addEventListener("compositionend", () => {
    state.isComposing = false;
});

clearButton.addEventListener("click", clearConversation);

document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
        inputEl.value = button.dataset.question || "";
        clearInputError();
        autoResizeInput();
        inputEl.focus();
    });
});

renderTraceView();
autoResizeInput();
inputEl.focus();
