function initializeApp() {
  if (window.lucide) {
    window.lucide.createIcons();
  } else {
    window.addEventListener("DOMContentLoaded", () => {
      if (window.lucide) {
        window.lucide.createIcons();
      }
    });
  }
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js");
  }

  initializeDeleteDialogs();
  initializePlanForms();
  initializeStudyStartButtons();

  const workspace = document.querySelector("[data-import-workspace]");
  if (!workspace) {
    return;
  }
  workspace.dataset.importReady = "true";

  const tabs = workspace.querySelectorAll("[data-import-tab]");
  const panels = workspace.querySelectorAll("[data-import-panel]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const selected = tab.dataset.importTab;
      tabs.forEach((candidate) => {
        const active = candidate === tab;
        candidate.setAttribute("aria-selected", String(active));
        candidate.classList.toggle("border-emerald-600", active);
        candidate.classList.toggle("text-emerald-700", active);
        candidate.classList.toggle("border-transparent", !active);
        candidate.classList.toggle("text-stone-500", !active);
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.importPanel !== selected;
      });
    });
  });

  const previewSection = document.querySelector("#import-preview");
  const summary = document.querySelector("#import-summary");
  const entriesContainer = document.querySelector("#import-entries");
  const errorsContainer = document.querySelector("#import-errors");
  const confirmButton = document.querySelector("#confirm-import");
  let pendingFormData = null;
  let pendingDigest = null;

  document.querySelectorAll("[data-import-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = form.querySelector('button[type="submit"]');
      submitButton.disabled = true;
      try {
        const formData = buildImportFormData(form);
        const response = await fetch("/api/v1/vocabularies/import/preview", {
          method: "POST",
          headers: csrfHeaders(workspace),
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error?.message || "解析失败");
        }
        pendingFormData = formData;
        pendingDigest = payload.preview_digest;
        renderPreview(payload);
      } catch (error) {
        renderFailure(error instanceof Error ? error.message : "解析失败");
      } finally {
        submitButton.disabled = false;
      }
    });
  });

  confirmButton.addEventListener("click", async () => {
    if (!pendingFormData || !pendingDigest) {
      return;
    }
    confirmButton.disabled = true;
    const formData = cloneFormData(pendingFormData);
    formData.append("preview_digest", pendingDigest);
    try {
      const response = await fetch("/api/v1/vocabularies/import", {
        method: "POST",
        headers: csrfHeaders(workspace),
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error?.message || "导入失败");
      }
      window.location.assign(`/vocabularies/${payload.vocabulary_id}`);
    } catch (error) {
      renderFailure(error instanceof Error ? error.message : "导入失败");
      confirmButton.disabled = false;
    }
  });

  function buildImportFormData(form) {
    const source = new FormData(form);
    source.set("duplicate_policy", "skip");
    if (form.dataset.mode !== "manual") {
      return source;
    }

    const entry = {};
    ["term", "meaning", "part_of_speech", "phonetic", "example", "tags"].forEach(
      (field) => {
        entry[field] = source.get(field) || "";
      },
    );
    entry.type = source.get("entry_type") || "";
    const result = new FormData();
    result.set("name", source.get("name"));
    result.set("duplicate_policy", "skip");
    result.set(
      "file",
      new File([JSON.stringify([entry])], "manual.json", {
        type: "application/json",
      }),
    );
    return result;
  }

  function cloneFormData(source) {
    const result = new FormData();
    source.forEach((value, key) => result.append(key, value));
    return result;
  }

  function csrfHeaders(element) {
    const token = element.dataset.csrfToken;
    return token ? { "X-CSRF-Token": token } : {};
  }

  function renderPreview(payload) {
    previewSection.hidden = false;
    summary.replaceChildren(
      metric("有效", payload.imported, "text-emerald-700"),
      metric("重复", payload.duplicated, "text-amber-700"),
      metric(
        "错误",
        payload.errors.filter((issue) => issue.code !== "DUPLICATE_TERM").length,
        "text-red-700",
      ),
    );

    entriesContainer.replaceChildren();
    if (payload.entries.length) {
      const title = document.createElement("h2");
      title.className = "mb-3 text-base font-semibold";
      title.textContent = "待导入词条";
      const list = document.createElement("div");
      list.className = "divide-y divide-stone-200 border-y border-stone-200";
      payload.entries.slice(0, 20).forEach((entry) => {
        const row = document.createElement("div");
        row.className = "grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-4 py-3";
        const term = document.createElement("strong");
        term.className = "break-words";
        term.textContent = entry.term;
        const meaning = document.createElement("span");
        meaning.className = "break-words text-stone-600";
        meaning.textContent = entry.meaning;
        row.append(term, meaning);
        list.append(row);
      });
      entriesContainer.append(title, list);
    }

    errorsContainer.replaceChildren();
    if (payload.errors.length) {
      const title = document.createElement("h2");
      title.className = "mb-3 text-base font-semibold text-red-800";
      title.textContent = "未导入的行";
      const list = document.createElement("ul");
      list.className = "space-y-2 text-sm";
      payload.errors.forEach((issue) => {
        const item = document.createElement("li");
        item.className = "border-l-2 border-red-300 pl-3 text-stone-700";
        item.textContent = `第 ${issue.line} 行：${issue.reason}`;
        list.append(item);
      });
      errorsContainer.append(title, list);
    }
    confirmButton.disabled = payload.imported === 0;
    previewSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderFailure(message) {
    previewSection.hidden = false;
    summary.replaceChildren();
    entriesContainer.replaceChildren();
    errorsContainer.replaceChildren();
    const alert = document.createElement("p");
    alert.className = "border-l-2 border-red-500 pl-3 text-red-800";
    alert.textContent = message;
    errorsContainer.append(alert);
    confirmButton.disabled = true;
  }

  function metric(label, value, colorClass) {
    const item = document.createElement("div");
    item.className = "border border-stone-200 bg-white p-3 text-center";
    const count = document.createElement("strong");
    count.className = `block text-xl ${colorClass}`;
    count.textContent = value;
    const caption = document.createElement("span");
    caption.className = "text-xs text-stone-500";
    caption.textContent = label;
    item.append(count, caption);
    return item;
  }
}

function initializeStudyStartButtons() {
  document.querySelectorAll("[data-start-study]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const token = button.dataset.csrfToken;
        const response = await fetch("/api/v1/study-sessions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { "X-CSRF-Token": token } : {}),
          },
          body: JSON.stringify({
            vocabulary_id: Number(button.dataset.vocabularyId),
            resume_existing: true,
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error?.message || "无法开始陪读");
        }
        window.location.assign(`/study/${payload.session.id}`);
      } catch (reason) {
        window.alert(reason instanceof Error ? reason.message : "无法开始陪读");
        button.disabled = false;
      }
    });
  });
}

function initializePlanForms() {
  document.querySelectorAll("[data-plan-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = form.querySelector('button[type="submit"]');
      const error = form.querySelector("[data-plan-error]");
      submitButton.disabled = true;
      error.hidden = true;
      error.textContent = "";

      const fields = form.elements;
      const payload = {
        daily_new_count: Number(fields.daily_new_count.value),
        daily_review_count: Number(fields.daily_review_count.value),
        interval_seconds: Number(fields.interval_seconds.value),
        is_random: fields.is_random.checked,
        is_loop: fields.is_loop.checked,
      };

      try {
        const token = form.dataset.csrfToken;
        const response = await fetch(form.dataset.endpoint, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { "X-CSRF-Token": token } : {}),
          },
          body: JSON.stringify(payload),
        });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error?.message || "保存失败");
        }
        window.location.assign(form.dataset.redirectUrl);
      } catch (reason) {
        error.textContent = reason instanceof Error ? reason.message : "保存失败";
        error.hidden = false;
        submitButton.disabled = false;
      }
    });
  });
}

function initializeDeleteDialogs() {
  const dialog = document.querySelector("[data-delete-dialog]");
  if (!dialog) {
    return;
  }

  const name = dialog.querySelector("[data-delete-name]");
  const error = dialog.querySelector("[data-delete-error]");
  const cancelButton = dialog.querySelector("[data-delete-cancel]");
  const confirmButton = dialog.querySelector("[data-delete-confirm]");
  let selected = null;

  document.querySelectorAll("[data-delete-trigger]").forEach((trigger) => {
    trigger.addEventListener("click", () => {
      selected = trigger;
      name.textContent = trigger.dataset.vocabularyName || "";
      error.hidden = true;
      error.textContent = "";
      confirmButton.disabled = false;
      dialog.showModal();
    });
  });

  cancelButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close();
    }
  });

  confirmButton.addEventListener("click", async () => {
    if (!selected) {
      return;
    }
    confirmButton.disabled = true;
    const vocabularyId = selected.dataset.vocabularyId;
    const token = selected.dataset.csrfToken;
    try {
      const response = await fetch(
        `/api/v1/vocabularies/${encodeURIComponent(vocabularyId)}?confirm_id=${encodeURIComponent(vocabularyId)}`,
        {
          method: "DELETE",
          headers: token ? { "X-CSRF-Token": token } : {},
        },
      );
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.error?.message || "删除失败");
      }
      window.location.assign(selected.dataset.redirectUrl || "/vocabularies");
    } catch (reason) {
      error.textContent = reason instanceof Error ? reason.message : "删除失败";
      error.hidden = false;
      confirmButton.disabled = false;
    }
  });
}

initializeApp();
