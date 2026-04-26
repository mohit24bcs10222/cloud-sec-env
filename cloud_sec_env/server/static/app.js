// PagerBench incident workbench — drives the live env via HTTP /reset and /step.

const els = {
  argumentsPreview: document.querySelector("#argumentsPreview"),
  callButton: document.querySelector("#callButton"),
  connStatus: document.querySelector("#connStatus"),
  copyButton: document.querySelector("#copyButton"),
  doneValue: document.querySelector("#doneValue"),
  episodeStatus: document.querySelector("#episodeStatus"),
  incidentPrompt: document.querySelector("#incidentPrompt"),
  incidentTitle: document.querySelector("#incidentTitle"),
  resetUiButton: document.querySelector("#resetUiButton"),
  rewardValue: document.querySelector("#rewardValue"),
  startButton: document.querySelector("#startButton"),
  stateJson: document.querySelector("#stateJson"),
  stateStep: document.querySelector("#stateStep"),
  stateTask: document.querySelector("#stateTask"),
  stateTools: document.querySelector("#stateTools"),
  stepCount: document.querySelector("#stepCount"),
  taskSelect: document.querySelector("#taskSelect"),
  toolDescription: document.querySelector("#toolDescription"),
  toolFields: document.querySelector("#toolFields"),
  toolSelect: document.querySelector("#toolSelect"),
  transcript: document.querySelector("#transcript"),
};

const state = {
  config: null,
  done: false,
  episodeStarted: false,
  lastObservation: null,
  lastReward: null,
  step: 0,
  toolsCalled: 0,
  totalReward: 0,
  transcript: [],
};

const TOOL_PRIORITY = [
  "logs_search",
  "trace_get",
  "metric_query",
  "ticket_search",
  "slack_search",
  "kb_search",
  "submit_answer",
];

function setConnStatus(label, mode) {
  els.connStatus.textContent = label;
  els.connStatus.className = `status-pill ${mode || ""}`;
}

function setEpisodeStatus(label, mode) {
  els.episodeStatus.textContent = label;
  els.episodeStatus.className = `status-pill ${mode || ""}`;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return response.json();
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return response.json();
}

async function loadConfig() {
  try {
    state.config = await getJson("/ui/config");
    setConnStatus("ready", "live");
  } catch (error) {
    setConnStatus("config error", "error");
    els.incidentPrompt.textContent = `Failed to load /ui/config: ${error.message}\n\nThe env may not have the workbench routes enabled. Try GET /docs for the API.`;
    return;
  }

  renderTasks();
  renderTools();
  if (state.config.tasks.length) {
    selectTask(state.config.default_task || state.config.tasks[0].task_name);
  }
  renderStatus();
}

function renderTasks() {
  els.taskSelect.innerHTML = state.config.tasks
    .map(
      (task) =>
        `<option value="${task.task_name}">${escapeHtml(task.label || task.task_name)}</option>`,
    )
    .join("");
}

function renderTools() {
  const sortedTools = state.config.tools.slice().sort((a, b) => {
    const ai = TOOL_PRIORITY.indexOf(a.name);
    const bi = TOOL_PRIORITY.indexOf(b.name);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
  state.config.tools = sortedTools;
  els.toolSelect.innerHTML = sortedTools
    .map((tool) => `<option value="${tool.name}">${tool.name}</option>`)
    .join("");
  renderToolForm();
}

function selectedTask() {
  return state.config.tasks.find((task) => task.task_name === els.taskSelect.value);
}

function selectTask(taskName) {
  els.taskSelect.value = taskName;
  const task = selectedTask();
  if (task) {
    els.incidentTitle.textContent = task.label || task.task_name;
    if (!state.episodeStarted) {
      els.incidentPrompt.textContent = task.preview || `Click "Reset Episode" to fetch the alert.`;
    }
  }
}

function currentTool() {
  return state.config.tools.find((tool) => tool.name === els.toolSelect.value);
}

function renderToolForm() {
  const tool = currentTool();
  if (!tool) {
    els.toolDescription.textContent = "";
    els.toolFields.innerHTML = "";
    renderArgumentPreview();
    return;
  }
  els.toolDescription.textContent = tool.description || "";

  const schema = tool.input_schema || {};
  const properties = schema.properties || {};
  const required = new Set(schema.required || []);

  els.toolFields.innerHTML = Object.entries(properties)
    .map(([name, prop]) => buildField(name, prop, required.has(name)))
    .join("");

  els.toolFields.querySelectorAll("input, select, textarea").forEach((input) => {
    input.addEventListener("input", renderArgumentPreview);
    input.addEventListener("change", renderArgumentPreview);
  });
  renderArgumentPreview();
}

function buildField(name, prop, isRequired) {
  const requiredMark = isRequired ? "required" : "optional";
  const label = `<span>${escapeHtml(prettyLabel(name))} <em>${requiredMark}</em></span>`;
  const placeholder = escapeHtml(prop.description || "");

  if (Array.isArray(prop.enum)) {
    const opts = ["", ...prop.enum]
      .map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v || "(none)")}</option>`)
      .join("");
    return `
      <label class="field tool-field" data-name="${name}" data-kind="string" data-enum="1">
        ${label}
        <select data-field="${name}">${opts}</select>
      </label>`;
  }

  if (prop.type === "integer" || prop.type === "number") {
    return `
      <label class="field tool-field" data-name="${name}" data-kind="${prop.type}">
        ${label}
        <input data-field="${name}" type="number" placeholder="${placeholder}" />
      </label>`;
  }

  // Long-text fields for submit_answer
  if (name === "root_cause" || name === "fix" || (prop.type === "string" && (prop.maxLength || 0) > 200)) {
    return `
      <label class="field tool-field" data-name="${name}" data-kind="string">
        ${label}
        <textarea data-field="${name}" rows="4" spellcheck="false" placeholder="${placeholder}"></textarea>
      </label>`;
  }

  return `
    <label class="field tool-field" data-name="${name}" data-kind="string">
      ${label}
      <input data-field="${name}" type="text" placeholder="${placeholder}" />
    </label>`;
}

function prettyLabel(name) {
  const overrides = {
    cloud: "Cloud",
    service: "Service",
    query: "Query",
    time_range: "Time range",
    limit: "Limit",
    trace_id: "Trace ID",
    metric_name: "Metric name",
    step: "Aggregation step",
    ticket_type: "Ticket type",
    channel: "Channel",
    root_cause: "Root cause",
    fix: "Fix",
  };
  return overrides[name] || name.replace(/_/g, " ");
}

function readArguments() {
  const args = {};
  els.toolFields.querySelectorAll("[data-field]").forEach((input) => {
    const name = input.dataset.field;
    const wrapper = input.closest(".tool-field");
    const kind = wrapper?.dataset.kind || "string";
    const raw = (input.value || "").trim();
    if (raw === "") return;
    if (kind === "integer") {
      const n = Number.parseInt(raw, 10);
      if (Number.isFinite(n)) args[name] = n;
    } else if (kind === "number") {
      const n = Number.parseFloat(raw);
      if (Number.isFinite(n)) args[name] = n;
    } else {
      args[name] = raw;
    }
  });
  return args;
}

function renderArgumentPreview() {
  try {
    els.argumentsPreview.textContent = JSON.stringify(readArguments(), null, 2);
    els.callButton.disabled = !state.episodeStarted || state.done;
  } catch (error) {
    els.argumentsPreview.textContent = `Invalid arguments: ${error.message}`;
    els.callButton.disabled = true;
  }
}

async function startEpisode() {
  els.startButton.disabled = true;
  setEpisodeStatus("resetting", "");
  state.transcript = [];
  state.step = 0;
  state.toolsCalled = 0;
  state.totalReward = 0;
  state.done = false;
  state.lastReward = null;
  state.lastObservation = null;
  renderTranscript();

  try {
    const result = await postJson("/reset", {});
    state.episodeStarted = true;
    state.lastObservation = result.observation || result;
    const obsContent = state.lastObservation.content || JSON.stringify(state.lastObservation, null, 2);
    els.incidentPrompt.textContent = obsContent;
    setEpisodeStatus("live", "live");
    setConnStatus("connected", "live");
    renderStatus();
  } catch (error) {
    setEpisodeStatus("reset failed", "error");
    setConnStatus("error", "error");
    els.incidentPrompt.textContent = `Reset failed: ${error.message}`;
  } finally {
    els.startButton.disabled = false;
  }
}

async function callTool() {
  if (!state.episodeStarted || state.done) return;
  const toolName = els.toolSelect.value;
  let args = {};
  try {
    args = readArguments();
  } catch (error) {
    alert(`Fix arguments first: ${error.message}`);
    return;
  }

  els.callButton.disabled = true;
  setEpisodeStatus("running", "");

  try {
    const payload = {
      action: { tool_name: toolName, arguments: args, reasoning: null },
    };
    const result = await postJson("/step", payload);
    const obs = result.observation || result;
    const reward = result.reward !== undefined ? result.reward : obs.reward;
    const done = Boolean(result.done || obs.done);

    state.step += 1;
    state.toolsCalled += 1;
    state.lastReward = reward ?? null;
    state.totalReward += Number(reward || 0);
    state.done = done;
    state.lastObservation = obs;

    state.transcript.push({
      index: state.step,
      toolName,
      args,
      content: obs.content || JSON.stringify(obs, null, 2),
      observation_type: obs.observation_type,
      reward,
      done,
      isTerminal: toolName === "submit_answer",
      isError: obs.observation_type === "error",
    });

    renderTranscript();
    renderStatus();
    if (done) {
      setEpisodeStatus("done", "live");
    } else {
      setEpisodeStatus("live", "live");
    }
  } catch (error) {
    state.transcript.push({
      index: state.step + 1,
      toolName,
      args,
      content: `Step failed: ${error.message}`,
      observation_type: "error",
      reward: null,
      done: false,
      isError: true,
    });
    renderTranscript();
    setEpisodeStatus("step error", "error");
  } finally {
    els.callButton.disabled = state.done || !state.episodeStarted;
  }
}

function renderTranscript() {
  if (!state.transcript.length) {
    els.transcript.className = "transcript-empty";
    els.transcript.innerHTML =
      'No tool calls yet. Click <strong style="color:var(--green)">Reset Episode</strong>, then call tools to investigate. End with <code>submit_answer</code> for the terminal reward.';
    return;
  }
  els.transcript.className = "transcript";
  els.transcript.innerHTML = state.transcript
    .map((entry) => {
      const reward =
        entry.reward === null || entry.reward === undefined ? "none" : Number(entry.reward).toFixed(3);
      const cls = [
        "transcript-item",
        entry.done ? "done" : "",
        entry.isError ? "error" : "",
        entry.isTerminal ? "terminal" : "",
      ]
        .filter(Boolean)
        .join(" ");
      const args = JSON.stringify(entry.args);
      return `
        <article class="${cls}">
          <div class="call-head">
            <span>${entry.index}</span>
            <strong>${escapeHtml(entry.toolName)}</strong>
            <em>reward ${reward}</em>
          </div>
          <code>${escapeHtml(args)}</code>
          <pre>${escapeHtml(entry.content || "")}</pre>
        </article>`;
    })
    .join("");
}

function renderStatus() {
  const maxSteps = state.config?.max_steps || 30;
  els.stepCount.textContent = `${state.step} / ${maxSteps}`;
  els.rewardValue.textContent =
    state.lastReward === null || state.lastReward === undefined ? "none" : Number(state.lastReward).toFixed(3);
  els.doneValue.textContent = String(state.done);
  els.callButton.disabled = state.done || !state.episodeStarted;

  els.stateTask.textContent = state.config?.tasks?.[0]?.task_name || "none";
  els.stateStep.textContent = String(state.step);
  els.stateTools.textContent = String(state.toolsCalled);
  if (state.lastObservation) {
    els.stateJson.textContent = JSON.stringify(
      {
        observation_type: state.lastObservation.observation_type,
        steps_remaining: state.lastObservation.steps_remaining,
        last_reward: state.lastReward,
        total_reward_accum: Number(state.totalReward.toFixed(3)),
        done: state.done,
      },
      null,
      2,
    );
  } else {
    els.stateJson.textContent = "{}";
  }
}

function copyTranscript() {
  const text = state.transcript
    .map((entry) => {
      return [
        `#${entry.index} ${entry.toolName}`,
        `args: ${JSON.stringify(entry.args)}`,
        `reward: ${entry.reward ?? "none"} done: ${entry.done}`,
        entry.content || "",
      ].join("\n");
    })
    .join("\n\n");
  navigator.clipboard.writeText(text || "");
}

function clearTranscriptUi() {
  state.transcript = [];
  state.step = 0;
  state.toolsCalled = 0;
  state.totalReward = 0;
  state.lastReward = null;
  state.done = false;
  state.episodeStarted = false;
  state.lastObservation = null;
  els.incidentPrompt.textContent = `Click "Reset Episode" to start a new episode.`;
  setEpisodeStatus("idle", "");
  renderTranscript();
  renderStatus();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

els.startButton.addEventListener("click", startEpisode);
els.callButton.addEventListener("click", callTool);
els.copyButton.addEventListener("click", copyTranscript);
els.resetUiButton.addEventListener("click", clearTranscriptUi);
els.taskSelect.addEventListener("change", () => selectTask(els.taskSelect.value));
els.toolSelect.addEventListener("change", renderToolForm);

loadConfig().catch((error) => {
  els.incidentPrompt.textContent = `Failed to bootstrap UI: ${error.message}`;
  setConnStatus("load error", "error");
});
