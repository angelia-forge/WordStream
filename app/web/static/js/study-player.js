(function () {
  "use strict";

  function remainingMilliseconds(deadline, now) {
    return Math.max(0, deadline - now);
  }

  function moveRetryItem(items, currentIndex) {
    if (currentIndex < 0 || currentIndex >= items.length) {
      throw new RangeError("currentIndex is outside the queue");
    }
    const [item] = items.splice(currentIndex, 1);
    const targetIndex = Math.min(currentIndex + 2, items.length);
    items.splice(targetIndex, 0, item);
    items.forEach((candidate, position) => {
      candidate.position = position;
    });
    return targetIndex;
  }

  class SpeechReader {
    constructor(rate, onModeChange) {
      this.rate = rate;
      this.onModeChange = onModeChange;
      this.engine = window.speechSynthesis;
      this.Utterance = window.SpeechSynthesisUtterance;
      this.mode = "waiting";
      this.pendingTerm = null;
      this.voiceWaitTimer = null;

      if (!this.engine || !this.Utterance) {
        this.setMode("silent");
        return;
      }
      this.refreshVoices();
      if (
        this.mode === "waiting" &&
        typeof this.engine.addEventListener === "function"
      ) {
        this.engine.addEventListener("voiceschanged", () => this.refreshVoices());
      }
      if (this.mode === "waiting") {
        this.voiceWaitTimer = window.setTimeout(() => {
          if (this.mode === "waiting") {
            this.setMode("silent");
          }
        }, 500);
      }
    }

    refreshVoices() {
      try {
        const voices = this.engine.getVoices();
        this.voices = voices;
        this.setMode(voices.length ? "ready" : "waiting");
        if (voices.length && this.voiceWaitTimer !== null) {
          window.clearTimeout(this.voiceWaitTimer);
          this.voiceWaitTimer = null;
        }
        if (voices.length && this.pendingTerm) {
          const term = this.pendingTerm;
          this.pendingTerm = null;
          this.speak(term);
        }
      } catch (_error) {
        this.setMode("silent");
      }
    }

    setMode(mode) {
      this.mode = mode;
      this.onModeChange(mode);
    }

    speak(term) {
      if (this.mode === "waiting") {
        this.pendingTerm = term;
        return;
      }
      if (this.mode !== "ready") {
        return;
      }
      try {
        this.engine.cancel();
        const utterance = new this.Utterance(term);
        utterance.rate = this.rate;
        utterance.lang = "en-US";
        const englishVoice = this.voices.find((voice) =>
          voice.lang.toLowerCase().startsWith("en"),
        );
        if (englishVoice) {
          utterance.voice = englishVoice;
        }
        this.engine.speak(utterance);
      } catch (_error) {
        this.setMode("silent");
      }
    }

    pause() {
      if (this.mode === "ready") {
        try {
          this.engine.pause();
        } catch (_error) {
          this.setMode("silent");
        }
      }
    }

    resume() {
      if (this.mode === "ready") {
        try {
          this.engine.resume();
        } catch (_error) {
          this.setMode("silent");
        }
      }
    }

    cancel() {
      if (this.engine) {
        try {
          this.engine.cancel();
        } catch (_error) {
          this.setMode("silent");
        }
      }
    }
  }

  class StudyPlayer {
    constructor(root, initialState) {
      this.root = root;
      this.session = initialState.session;
      this.items = initialState.items;
      this.currentIndex = this.items.findIndex((item) => item.result === null);
      if (this.currentIndex < 0) {
        this.currentIndex = this.items.length;
      }
      this.displayIndex = Math.min(this.currentIndex, this.items.length - 1);
      if (
        this.currentIndex >= this.items.length &&
        this.session.plan_snapshot.is_loop
      ) {
        this.displayIndex = 0;
      }
      this.intervalMs = this.session.plan_snapshot.interval_seconds * 1000;
      this.remainingMs = this.intervalMs;
      this.deadline = null;
      this.timerId = null;
      this.paused = this.session.status !== "active";
      this.sessionId = Number(root.dataset.sessionId);
      this.outboxKey = `wordstream.study.outbox.${this.sessionId}`;
      this.pending = this.loadOutbox();
      this.settledSinceFlush = 0;
      this.flushPromise = null;
      this.transitioning = false;
      this.finished = this.session.status === "finished";
      this.csrfToken = root.dataset.csrfToken || "";
      this.vocabularyId = Number(root.dataset.vocabularyId);
      this.elements = this.collectElements();
      this.speech = new SpeechReader(
        Number(root.dataset.ttsRate || "1"),
        (mode) => this.renderSpeechMode(mode),
      );
    }

    collectElements() {
      const find = (selector) => this.root.querySelector(selector);
      return {
        progress: find("[data-study-progress]"),
        remaining: find("[data-study-remaining]"),
        source: find("[data-study-source]"),
        term: find("[data-study-term]"),
        pos: find("[data-study-pos]"),
        phonetic: find("[data-study-phonetic]"),
        meaning: find("[data-study-meaning]"),
        example: find("[data-study-example]"),
        error: find("[data-study-error]"),
        previous: find("[data-study-previous]"),
        next: find("[data-study-next]"),
        again: find("[data-study-again]"),
        toggle: find("[data-study-toggle]"),
        toggleIcon: find("[data-study-toggle-icon]"),
        toggleLabel: find("[data-study-toggle-label]"),
        finish: find("[data-study-finish]"),
        speechStatus: find("[data-tts-status]"),
      };
    }

    async start() {
      this.elements.previous.addEventListener("click", () => this.previous());
      this.elements.next.addEventListener("click", () => this.advance());
      this.elements.again.addEventListener("click", () => this.markAgain());
      this.elements.toggle.addEventListener("click", () => this.togglePause());
      this.elements.finish.addEventListener("click", () => this.finish());
      document.addEventListener("visibilitychange", () =>
        this.handleVisibilityChange(),
      );
      window.addEventListener("online", () => {
        this.flushOutcomes().catch(() => {});
      });
      window.addEventListener("pagehide", () => {
        this.clearTimer();
        this.flushOutcomes(true).catch(() => {});
      });

      this.render();
      if (this.pending.length) {
        this.paused = true;
        this.renderPauseButton();
        try {
          await this.flushOutcomes();
          await this.refreshSession();
          this.paused = this.session.status !== "active";
          this.finished = this.session.status === "finished";
          this.render();
        } catch (_error) {
          return;
        }
      }
      if (!this.paused && this.currentIndex < this.items.length) {
        this.speech.speak(this.currentItem().entry.term);
        this.resetTimer();
      } else if (
        !this.paused &&
        this.session.plan_snapshot.is_loop &&
        this.items.length
      ) {
        this.speech.speak(this.currentItem().entry.term);
        this.resetTimer();
      }
    }

    currentItem() {
      return this.items[this.displayIndex];
    }

    render() {
      const item = this.currentItem();
      if (!item) {
        this.showError("本次会话没有可播放的词条");
        return;
      }
      const entry = item.entry;
      this.elements.progress.textContent = `第 ${this.displayIndex + 1} / ${this.items.length} 个`;
      this.elements.remaining.textContent =
        this.currentIndex >= this.items.length
          ? "本轮已播放完"
          : `会话剩余 ${this.items.length - this.currentIndex} 个`;
      this.elements.source.textContent =
        item.source === "review" ? "复习" : "新词";
      this.elements.term.textContent = entry.term;
      this.elements.pos.textContent = entry.part_of_speech || "";
      this.elements.phonetic.textContent = entry.phonetic || "";
      this.elements.meaning.textContent = entry.meaning;
      this.elements.example.textContent = entry.example || "";
      this.elements.example.hidden = !entry.example;
      this.elements.previous.disabled = this.displayIndex <= 0;
      this.elements.next.disabled = this.finished;
      this.elements.again.disabled =
        this.finished ||
        this.currentIndex >= this.items.length ||
        this.displayIndex !== this.currentIndex;
      this.elements.toggle.disabled = this.finished;
      this.renderPauseButton();
    }

    renderPauseButton() {
      const action = this.paused ? "继续" : "暂停";
      this.elements.toggle.title = action;
      this.elements.toggleLabel.textContent = action;
      this.elements.toggleIcon.setAttribute(
        "data-lucide",
        this.paused ? "play" : "pause",
      );
      if (window.lucide) {
        window.lucide.createIcons();
      }
    }

    renderSpeechMode(mode) {
      const labels = {
        ready: "朗读模式",
        waiting: "语音准备中",
        silent: "静默模式",
      };
      this.elements.speechStatus.textContent = labels[mode];
    }

    previous() {
      if (this.displayIndex <= 0 || this.finished) {
        return;
      }
      this.displayIndex -= 1;
      this.switchDisplayedItem();
    }

    async advance() {
      if (this.transitioning || this.finished) {
        return;
      }
      if (this.displayIndex < this.currentIndex) {
        this.displayIndex += 1;
        if (this.displayIndex >= this.items.length) {
          this.handleQueueEnd();
          return;
        }
        this.switchDisplayedItem();
        return;
      }
      if (this.currentIndex >= this.items.length) {
        this.advanceCompletedLoop();
        return;
      }

      this.transitioning = true;
      try {
        const item = this.items[this.currentIndex];
        const newlySettled = item.result === null;
        if (newlySettled) {
          this.enqueue(item, "seen");
          item.result = "seen";
          this.settledSinceFlush += 1;
        }
        item.attempt_count += 1;
        this.currentIndex += 1;
        this.displayIndex = Math.min(this.currentIndex, this.items.length - 1);
        if (this.settledSinceFlush >= 10) {
          this.flushOutcomes().catch(() => {});
        }
        if (this.currentIndex >= this.items.length) {
          this.handleQueueEnd();
        } else {
          this.switchDisplayedItem();
        }
      } finally {
        this.transitioning = false;
      }
    }

    markAgain() {
      if (
        this.transitioning ||
        this.finished ||
        this.displayIndex !== this.currentIndex ||
        this.currentIndex >= this.items.length
      ) {
        return;
      }
      const item = this.items[this.currentIndex];
      const newlySettled = item.result === null;
      this.enqueue(item, "again");
      if (newlySettled) {
        item.result = "again";
        this.settledSinceFlush += 1;
      }
      item.attempt_count += 1;
      moveRetryItem(this.items, this.currentIndex);
      this.displayIndex = this.currentIndex;
      if (this.settledSinceFlush >= 10) {
        this.flushOutcomes().catch(() => {});
      }
      this.switchDisplayedItem();
    }

    enqueue(item, result) {
      this.pending.push({
        session_item_id: item.id,
        client_event_id: crypto.randomUUID(),
        result,
        attempt_count: item.attempt_count + 1,
        occurred_at: new Date().toISOString(),
      });
      this.saveOutbox();
    }

    loadOutbox() {
      try {
        const value = JSON.parse(window.localStorage.getItem(this.outboxKey));
        return Array.isArray(value)
          ? value.filter(
              (outcome) =>
                outcome &&
                typeof outcome.session_item_id === "string" &&
                typeof outcome.client_event_id === "string" &&
                (outcome.result === "seen" || outcome.result === "again") &&
                Number.isInteger(outcome.attempt_count) &&
                typeof outcome.occurred_at === "string",
            )
          : [];
      } catch (_error) {
        return [];
      }
    }

    saveOutbox() {
      try {
        if (this.pending.length) {
          window.localStorage.setItem(
            this.outboxKey,
            JSON.stringify(this.pending),
          );
        } else {
          window.localStorage.removeItem(this.outboxKey);
        }
      } catch (_error) {
        this.showError("无法在本机保存待同步进度");
      }
    }

    async togglePause() {
      if (this.paused) {
        this.paused = false;
        this.speech.cancel();
        this.speech.speak(this.currentItem().entry.term);
        this.startTimer(this.remainingMs);
      } else {
        this.paused = true;
        this.remainingMs =
          this.deadline === null
            ? this.intervalMs
            : remainingMilliseconds(this.deadline, Date.now());
        this.clearTimer();
        this.speech.pause();
        await this.flushOutcomes();
      }
      this.renderPauseButton();
    }

    switchDisplayedItem() {
      this.speech.cancel();
      this.remainingMs = this.intervalMs;
      this.render();
      if (!this.paused) {
        this.speech.speak(this.currentItem().entry.term);
        this.resetTimer();
      }
    }

    handleQueueEnd() {
      if (this.session.plan_snapshot.is_loop && this.items.length) {
        this.displayIndex = 0;
        this.switchDisplayedItem();
        return;
      }
      this.paused = true;
      this.remainingMs = this.intervalMs;
      this.clearTimer();
      this.speech.cancel();
      this.render();
    }

    advanceCompletedLoop() {
      if (!this.session.plan_snapshot.is_loop || !this.items.length) {
        this.handleQueueEnd();
        return;
      }
      this.displayIndex = (this.displayIndex + 1) % this.items.length;
      this.switchDisplayedItem();
    }

    resetTimer() {
      this.startTimer(this.intervalMs);
    }

    startTimer(milliseconds) {
      this.clearTimer();
      this.remainingMs = milliseconds;
      this.deadline = Date.now() + milliseconds;
      this.timerId = window.setTimeout(() => {
        this.timerId = null;
        this.advance();
      }, milliseconds);
    }

    clearTimer() {
      if (this.timerId !== null) {
        window.clearTimeout(this.timerId);
        this.timerId = null;
      }
    }

    handleVisibilityChange() {
      if (document.hidden) {
        this.clearTimer();
        this.speech.cancel();
        this.flushOutcomes(true);
        return;
      }
      if (this.paused || this.finished) {
        return;
      }
      const remaining =
        this.deadline === null
          ? this.intervalMs
          : remainingMilliseconds(this.deadline, Date.now());
      if (remaining === 0) {
        this.advance();
      } else {
        this.speech.speak(this.currentItem().entry.term);
        this.startTimer(remaining);
      }
    }

    async flushOutcomes(keepalive = false) {
      if (this.flushPromise) {
        await this.flushPromise;
      }
      if (!this.pending.length) {
        return;
      }
      this.flushPromise = this.performFlush(keepalive);
      try {
        await this.flushPromise;
      } finally {
        this.flushPromise = null;
      }
    }

    async performFlush(keepalive) {
      const outcomes = this.pending.slice();
      try {
        await this.sendBatchWithRetry(outcomes, keepalive);
        const confirmedIds = new Set(
          outcomes.map((outcome) => outcome.client_event_id),
        );
        this.pending = this.pending.filter(
          (outcome) => !confirmedIds.has(outcome.client_event_id),
        );
        this.saveOutbox();
        this.settledSinceFlush = 0;
      } catch (error) {
        this.paused = true;
        this.clearTimer();
        this.speech.pause();
        this.renderPauseButton();
        this.showError(
          error instanceof TypeError
            ? "学习进度同步失败"
            : error instanceof Error
              ? error.message
              : "学习进度同步失败",
        );
        throw error;
      }
    }

    async sendBatchWithRetry(outcomes, keepalive) {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const response = await fetch(
            `/api/v1/study-sessions/${this.sessionId}/outcomes/batch`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                ...(this.csrfToken
                  ? { "X-CSRF-Token": this.csrfToken }
                  : {}),
              },
              body: JSON.stringify({ outcomes }),
              keepalive,
            },
          );
          const payload = await response.json().catch(() => ({}));
          if (response.ok) {
            return payload;
          }
          const code = payload.error?.code;
          if (
            code === "OUTCOME_ALREADY_RECORDED" ||
            code === "IDEMPOTENCY_CONFLICT"
          ) {
            this.discardConflict(outcomes, payload.error?.details);
            await this.refreshSession();
            throw new Error(payload.error?.message || "学习进度存在冲突");
          }
          if (response.status < 500 && code !== "DATABASE_BUSY") {
            throw new Error(payload.error?.message || "学习进度同步失败");
          }
          throw new TypeError(payload.error?.message || "学习进度同步失败");
        } catch (error) {
          if (attempt === 2 || !this.isRetryableError(error)) {
            throw error;
          }
        }
        await new Promise((resolve) =>
          window.setTimeout(resolve, 250 * 2 ** attempt),
        );
      }
    }

    isRetryableError(error) {
      return error instanceof TypeError;
    }

    discardConflict(outcomes, details) {
      if (!details?.session_item_id && !details?.client_event_id) {
        return;
      }
      const conflicted = outcomes.filter(
        (outcome) =>
          outcome.session_item_id === details.session_item_id ||
          outcome.client_event_id === details.client_event_id,
      );
      const discardedIds = new Set(
        conflicted.map((outcome) => outcome.client_event_id),
      );
      this.pending = this.pending.filter(
        (outcome) => !discardedIds.has(outcome.client_event_id),
      );
      this.saveOutbox();
    }

    async refreshSession() {
      const response = await fetch(
        `/api/v1/study-sessions/${this.sessionId}`,
      );
      if (!response.ok) {
        throw new Error("无法刷新学习会话");
      }
      const state = await response.json();
      this.session = state.session;
      this.items = state.items;
      this.currentIndex = this.items.findIndex((item) => item.result === null);
      if (this.currentIndex < 0) {
        this.currentIndex = this.items.length;
      }
      this.displayIndex = Math.min(this.currentIndex, this.items.length - 1);
      this.render();
    }

    async finish() {
      if (this.transitioning || this.finished) {
        return;
      }
      this.transitioning = true;
      this.paused = true;
      this.clearTimer();
      this.speech.cancel();
      this.elements.finish.disabled = true;
      try {
        await this.flushOutcomes();
        const response = await fetch(
          `/api/v1/study-sessions/${this.sessionId}/finish`,
          {
            method: "POST",
            headers: this.csrfToken
              ? { "X-CSRF-Token": this.csrfToken }
              : {},
          },
        );
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error?.message || "结束会话失败");
        }
        this.finished = true;
        window.location.assign(
          `/vocabularies/${this.vocabularyId}?study_finished=1`,
        );
      } catch (error) {
        this.showError(error instanceof Error ? error.message : "结束会话失败");
        this.elements.finish.disabled = false;
        this.transitioning = false;
      }
    }

    showError(message) {
      this.elements.error.textContent = message;
      this.elements.error.hidden = false;
    }
  }

  function initializeStudyPlayer() {
    const root = document.querySelector("[data-study-player]");
    const data = document.querySelector("#study-session-data");
    if (!root || !data) {
      return;
    }
    const player = new StudyPlayer(root, JSON.parse(data.textContent));
    window.wordStreamStudyPlayer = player;
    player.start();
  }

  window.WordStreamPlayerInternals = {
    remainingMilliseconds,
    moveRetryItem,
    SpeechReader,
  };
  initializeStudyPlayer();
})();
