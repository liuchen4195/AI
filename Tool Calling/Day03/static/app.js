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
        const trace = view.trace;
        if (!trace) {
            renderTraceState("failed", "本轮失败", "未获取到本轮轨迹。");
            return;
        }

        const labels = {
            success: "本轮成功",
            partial: "本轮部分成功",
            failed: "本轮失败",
        };
        const kinds = {
            success: "done",
            partial: "partial",
            failed: "failed",
        };
        const status = trace.status || "success";
        const failedMessage = trace.error && trace.error.message;
        const detail = status === "failed" && failedMessage
            ? failedMessage
            : "本轮轨迹已记录，详细统计与调用详情将在步骤 8、9 展示。";

        renderTraceState(
            kinds[status] || "done",
            labels[status] || "本轮已完成",
            detail
        );
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
