const state = {
  filters: {
    dateFrom: "",
    dateTo: "",
    timeOfDay: "",
    provider: "",
    specialty: "",
    sortBy: "date",
    sortDir: "asc",
  },
  results: {
    page: 1,
    pageSize: 10,
    total: 0,
    totalPages: 1,
    items: [],
    latestLatencyMs: 0,
    metrics: null,
  },
  calendar: {
    view: window.innerWidth < 768 ? "week" : "month",
    anchorDate: new Date().toISOString().slice(0, 10),
    touchStartX: 0,
  },
  selectedSlot: null,
  reservationToken: "",
  reservationExpiresAt: "",
  reservationTimerId: null,
  suggestions: [],
  integrations: {
    google: { connected: false, status: "revoked" },
    outlook: { connected: false, status: "revoked" },
  },
};

const elements = {
  form: document.getElementById("searchFilters"),
  dateFrom: document.getElementById("dateFrom"),
  dateTo: document.getElementById("dateTo"),
  timeOfDay: document.getElementById("timeOfDay"),
  provider: document.getElementById("provider"),
  providerSuggestions: document.getElementById("providerSuggestions"),
  specialty: document.getElementById("specialty"),
  sortBy: document.getElementById("sortBy"),
  sortDir: document.getElementById("sortDir"),
  filterSummary: document.getElementById("filterSummary"),
  clearFiltersButton: document.getElementById("clearFiltersButton"),
  resultsSummary: document.getElementById("resultsSummary"),
  searchMetricsSummary: document.getElementById("searchMetricsSummary"),
  searchResults: document.getElementById("searchResults"),
  searchEmptyState: document.getElementById("searchEmptyState"),
  previousPageButton: document.getElementById("previousPageButton"),
  nextPageButton: document.getElementById("nextPageButton"),
  paginationLabel: document.getElementById("paginationLabel"),
  expandDateRangeButton: document.getElementById("expandDateRangeButton"),
  clearEmptyStateFiltersButton: document.getElementById("clearEmptyStateFiltersButton"),
  calendarGrid: document.getElementById("calendarGrid"),
  calendarRangeLabel: document.getElementById("calendarRangeLabel"),
  timezoneLabel: document.getElementById("timezoneLabel"),
  calendarFootnote: document.getElementById("calendarFootnote"),
  monthViewButton: document.getElementById("monthViewButton"),
  weekViewButton: document.getElementById("weekViewButton"),
  previousRangeButton: document.getElementById("previousRangeButton"),
  nextRangeButton: document.getElementById("nextRangeButton"),
  selectedSlotDetails: document.getElementById("selectedSlotDetails"),
  bookingSummary: document.getElementById("bookingSummary"),
  checkoutForm: document.getElementById("checkoutForm"),
  reserveSlotButton: document.getElementById("reserveSlotButton"),
  bookNowButton: document.getElementById("bookNowButton"),
  reservationCountdown: document.getElementById("reservationCountdown"),
  checkoutStatusMessage: document.getElementById("checkoutStatusMessage"),
  preferredSlotId: document.getElementById("preferredSlotId"),
  providerDialog: document.getElementById("providerDialog"),
  providerDialogBody: document.getElementById("providerDialogBody"),
  googleBadge: document.getElementById("googleIntegrationBadge"),
  outlookBadge: document.getElementById("outlookIntegrationBadge"),
  connectGoogleButton: document.getElementById("connectGoogleButton"),
  disconnectGoogleButton: document.getElementById("disconnectGoogleButton"),
  connectOutlookButton: document.getElementById("connectOutlookButton"),
  disconnectOutlookButton: document.getElementById("disconnectOutlookButton"),
  integrationStatusMessage: document.getElementById("integrationStatusMessage"),
  processConfirmationsButton: document.getElementById("processConfirmationsButton"),
  processRemindersButton: document.getElementById("processRemindersButton"),
  processSwapsButton: document.getElementById("processSwapsButton"),
  processCalendarSyncButton: document.getElementById("processCalendarSyncButton"),
  refreshMetricsButton: document.getElementById("refreshMetricsButton"),
  dashboardMetrics: document.getElementById("dashboardMetrics"),
  opsStatusMessage: document.getElementById("opsStatusMessage"),
  refreshClinicalButton: document.getElementById("refreshClinicalButton"),
  uploadDocumentButton: document.getElementById("uploadDocumentButton"),
  aggregateProfileButton: document.getElementById("aggregateProfileButton"),
  detectConflictsButton: document.getElementById("detectConflictsButton"),
  suggestCodesButton: document.getElementById("suggestCodesButton"),
  reviewQueueButton: document.getElementById("reviewQueueButton"),
  configureThresholdButton: document.getElementById("configureThresholdButton"),
  refreshConflictQueueButton: document.getElementById("refreshConflictQueueButton"),
  conflictSeverityFilter: document.getElementById("conflictSeverityFilter"),
  clinicalStatusMessage: document.getElementById("clinicalStatusMessage"),
  uploadDocumentDialog: document.getElementById("uploadDocumentDialog"),
  uploadDocumentForm: document.getElementById("uploadDocumentForm"),
  closeUploadDialogButton: document.getElementById("closeUploadDialogButton"),
  uploadProgressMessage: document.getElementById("uploadProgressMessage"),
  thresholdDialog: document.getElementById("thresholdDialog"),
  thresholdForm: document.getElementById("thresholdForm"),
  icd10Threshold: document.getElementById("icd10Threshold"),
  cptThreshold: document.getElementById("cptThreshold"),
  icd10ThresholdLabel: document.getElementById("icd10ThresholdLabel"),
  cptThresholdLabel: document.getElementById("cptThresholdLabel"),
  thresholdReason: document.getElementById("thresholdReason"),
  closeThresholdDialogButton: document.getElementById("closeThresholdDialogButton"),
  thresholdHistory: document.getElementById("thresholdHistory"),
  thresholdMessage: document.getElementById("thresholdMessage"),
  conflictResolutionDialog: document.getElementById("conflictResolutionDialog"),
  conflictComparison: document.getElementById("conflictComparison"),
  conflictResolutionForm: document.getElementById("conflictResolutionForm"),
  conflictAction: document.getElementById("conflictAction"),
  selectedConflictVersion: document.getElementById("selectedConflictVersion"),
  conflictResolutionNotes: document.getElementById("conflictResolutionNotes"),
  closeConflictDialogButton: document.getElementById("closeConflictDialogButton"),
  conflictResolutionMessage: document.getElementById("conflictResolutionMessage"),
  overviewContent: document.getElementById("overviewContent"),
  medicationsContent: document.getElementById("medicationsContent"),
  allergiesContent: document.getElementById("allergiesContent"),
  diagnosesContent: document.getElementById("diagnosesContent"),
  conflictsContent: document.getElementById("conflictsContent"),
  codesContent: document.getElementById("codesContent"),
  documentsContent: document.getElementById("documentsContent"),
  clinicalTabs: Array.from(document.querySelectorAll(".clinical-tab")),
  clinicalTabPanels: Array.from(document.querySelectorAll(".clinical-tab-panel")),
};

let filterDebounceId;
let suggestionDebounceId;

bootstrap().catch((error) => {
  console.error(error);
  elements.checkoutStatusMessage.textContent = "The booking experience could not be initialized.";
});

async function bootstrap() {
  hydrateFromQuery();
  applyFilterInputs();
  await Promise.all([loadPatientProfile(), loadSpecialties(), loadIntegrations()]);
  bindEvents();
  renderFilterSummary();
  await Promise.all([renderSearchResults(), renderCalendar()]);
  await refreshMetrics();
  await loadClinicalProfile();
}

function bindEvents() {
  elements.form.addEventListener("input", onFilterInput);
  elements.clearFiltersButton.addEventListener("click", clearFilters);
  elements.previousPageButton.addEventListener("click", () => changePage(-1));
  elements.nextPageButton.addEventListener("click", () => changePage(1));
  elements.expandDateRangeButton.addEventListener("click", expandDateRange);
  elements.clearEmptyStateFiltersButton.addEventListener("click", clearFilters);
  elements.monthViewButton.addEventListener("click", () => setCalendarView("month"));
  elements.weekViewButton.addEventListener("click", () => setCalendarView("week"));
  elements.previousRangeButton.addEventListener("click", () => shiftCalendar(-1));
  elements.nextRangeButton.addEventListener("click", () => shiftCalendar(1));
  elements.calendarGrid.addEventListener("touchstart", onCalendarTouchStart, { passive: true });
  elements.calendarGrid.addEventListener("touchend", onCalendarTouchEnd, { passive: true });
  elements.reserveSlotButton.addEventListener("click", reserveSelectedSlot);
  elements.checkoutForm.addEventListener("submit", onBookNow);
  elements.connectGoogleButton.addEventListener("click", () => connectProvider("google"));
  elements.connectOutlookButton.addEventListener("click", () => connectProvider("outlook"));
  elements.disconnectGoogleButton.addEventListener("click", () => disconnectProvider("google"));
  elements.disconnectOutlookButton.addEventListener("click", () => disconnectProvider("outlook"));
  elements.processConfirmationsButton.addEventListener("click", () => runOpsJob("/api/jobs/process-confirmations", "Confirmation queue processed."));
  elements.processRemindersButton.addEventListener("click", () => runOpsJob("/api/jobs/process-reminders", "Reminder engine processed."));
  elements.processSwapsButton.addEventListener("click", () => runOpsJob("/api/jobs/process-swaps", "Preferred slot swap engine processed."));
  elements.processCalendarSyncButton.addEventListener("click", () => runOpsJob("/api/jobs/process-calendar-sync", "Calendar sync queue processed."));
  elements.refreshMetricsButton.addEventListener("click", refreshMetrics);
  elements.provider.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      clearSuggestions();
    }
  });

  if (elements.refreshClinicalButton) {
    elements.refreshClinicalButton.addEventListener("click", loadClinicalProfile);
    elements.aggregateProfileButton.addEventListener("click", aggregateClinicalProfile);
    elements.detectConflictsButton.addEventListener("click", detectClinicalConflicts);
    elements.suggestCodesButton.addEventListener("click", suggestMedicalCodes);
    elements.reviewQueueButton.addEventListener("click", loadReviewQueue);
    elements.configureThresholdButton.addEventListener("click", openThresholdDialog);
    elements.refreshConflictQueueButton.addEventListener("click", () => loadConflictQueue(true));
    elements.conflictSeverityFilter.addEventListener("change", () => loadConflictQueue(false));
    elements.uploadDocumentButton.addEventListener("click", () => elements.uploadDocumentDialog.showModal());
    elements.closeUploadDialogButton.addEventListener("click", () => elements.uploadDocumentDialog.close());
    elements.uploadDocumentForm.addEventListener("submit", handleDocumentUpload);
    elements.closeThresholdDialogButton.addEventListener("click", () => elements.thresholdDialog.close());
    elements.thresholdForm.addEventListener("submit", saveThresholdConfiguration);
    elements.icd10Threshold.addEventListener("input", () => {
      elements.icd10ThresholdLabel.textContent = Number(elements.icd10Threshold.value).toFixed(2);
    });
    elements.cptThreshold.addEventListener("input", () => {
      elements.cptThresholdLabel.textContent = Number(elements.cptThreshold.value).toFixed(2);
    });
    elements.closeConflictDialogButton.addEventListener("click", () => elements.conflictResolutionDialog.close());
    elements.conflictResolutionForm.addEventListener("submit", submitConflictResolution);
    elements.clinicalTabs.forEach((tab, index) => {
      tab.addEventListener("click", () => switchClinicalTab(index));
    });
  }
}

function hydrateFromQuery() {
  const params = new URLSearchParams(window.location.search);
  ["dateFrom", "dateTo", "timeOfDay", "provider", "specialty"].forEach((key) => {
    if (params.has(key)) {
      state.filters[key] = params.get(key);
    }
  });
  if (params.has("sortBy")) {
    state.filters.sortBy = params.get("sortBy");
  }
  if (params.has("sortDir")) {
    state.filters.sortDir = params.get("sortDir");
  }
  if (params.has("page")) {
    state.results.page = Math.max(1, Number(params.get("page")) || 1);
  }
}

function applyFilterInputs() {
  elements.dateFrom.value = state.filters.dateFrom;
  elements.dateTo.value = state.filters.dateTo;
  elements.timeOfDay.value = state.filters.timeOfDay;
  elements.provider.value = state.filters.provider;
  elements.sortBy.value = state.filters.sortBy;
  elements.sortDir.value = state.filters.sortDir;
}

async function loadPatientProfile() {
  const payload = await fetchJson("/api/patient/profile");
  if (!payload.success) return;
  document.getElementById("firstName").value = payload.data.first_name || "";
  document.getElementById("lastName").value = payload.data.last_name || "";
  document.getElementById("email").value = payload.data.email || "";
  document.getElementById("phone").value = payload.data.phone || "";
  document.getElementById("timezone").value = payload.data.preferred_timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  const channels = JSON.parse(payload.data.reminder_channels || "[]");
  document.querySelectorAll('input[name="reminderChannel"]').forEach((checkbox) => {
    checkbox.checked = channels.includes(checkbox.value);
  });
}

async function loadSpecialties() {
  const payload = await fetchJson("/api/appointments/specialties");
  if (!payload.success) return;
  payload.data.forEach((specialty) => {
    const option = document.createElement("option");
    option.value = specialty.name;
    option.textContent = specialty.name;
    elements.specialty.appendChild(option);
  });
  elements.specialty.value = state.filters.specialty;
}

async function loadIntegrations() {
  const payload = await fetchJson("/api/integrations/status");
  if (!payload.success) return;
  state.integrations = payload.data;
  renderIntegrationState();
}

function renderIntegrationState() {
  updateIntegrationBadge("google", state.integrations.google);
  updateIntegrationBadge("outlook", state.integrations.outlook);
}

function updateIntegrationBadge(provider, details) {
  const badge = provider === "google" ? elements.googleBadge : elements.outlookBadge;
  badge.textContent = details.connected ? "Connected" : details.status === "error" ? "Connection Error" : "Not Connected";
  badge.className = `badge ${details.connected ? "badge--success" : details.status === "error" ? "badge--warning" : ""}`;
}

function onFilterInput(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  syncFiltersFromInputs();
  renderFilterSummary();
  if (target.id === "provider") {
    clearTimeout(suggestionDebounceId);
    suggestionDebounceId = setTimeout(loadProviderSuggestions, 220);
  }
  clearTimeout(filterDebounceId);
  filterDebounceId = setTimeout(async () => {
    await Promise.all([renderSearchResults(), renderCalendar()]);
  }, 220);
}

function syncFiltersFromInputs() {
  state.filters.dateFrom = elements.dateFrom.value;
  state.filters.dateTo = elements.dateTo.value;
  state.filters.timeOfDay = elements.timeOfDay.value;
  state.filters.provider = elements.provider.value.trim();
  state.filters.specialty = elements.specialty.value;
  state.filters.sortBy = elements.sortBy.value;
  state.filters.sortDir = elements.sortDir.value;
  state.results.page = 1;
  writeQueryState();
}

function renderFilterSummary() {
  const parts = [];
  if (state.filters.dateFrom || state.filters.dateTo) {
    parts.push(`Date: ${state.filters.dateFrom || "Any"} to ${state.filters.dateTo || "Any"}`);
  }
  if (state.filters.timeOfDay) parts.push(`Time: ${state.filters.timeOfDay}`);
  if (state.filters.provider) parts.push(`Provider: ${state.filters.provider}`);
  if (state.filters.specialty) parts.push(`Specialty: ${state.filters.specialty}`);
  elements.filterSummary.textContent = parts.length ? parts.join(" | ") : "No active filters.";
}

function writeQueryState() {
  const params = new URLSearchParams();
  Object.entries(state.filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  if (state.results.page > 1) {
    params.set("page", String(state.results.page));
  }
  history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
}

async function loadProviderSuggestions() {
  const query = state.filters.provider;
  if (query.length < 2) {
    clearSuggestions();
    return;
  }
  const payload = await fetchJson(`/api/providers/suggest?query=${encodeURIComponent(query)}`);
  clearSuggestions();
  if (!payload.success || !payload.data.length) return;
  payload.data.forEach((provider) => {
    const item = document.createElement("li");
    item.className = "suggestion-item";
    item.setAttribute("role", "option");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${provider.name} (${provider.specialty})`;
    button.addEventListener("click", async () => {
      elements.provider.value = provider.name;
      state.filters.provider = provider.name;
      state.results.page = 1;
      writeQueryState();
      clearSuggestions();
      await Promise.all([renderSearchResults(), renderCalendar()]);
    });
    item.appendChild(button);
    elements.providerSuggestions.appendChild(item);
  });
  elements.provider.setAttribute("aria-expanded", "true");
}

function clearSuggestions() {
  elements.providerSuggestions.innerHTML = "";
  elements.provider.setAttribute("aria-expanded", "false");
}

async function renderSearchResults() {
  renderFilterSummary();
  const params = new URLSearchParams({
    ...state.filters,
    page: String(state.results.page),
    pageSize: String(state.results.pageSize),
  });
  const payload = await fetchJson(`/api/appointments/search?${params.toString()}`);
  if (!payload.success) {
    elements.searchResults.innerHTML = `<article class="result-card result-card--error"><h3>Search unavailable</h3><p>${payload.error.message}</p></article>`;
    elements.searchEmptyState.hidden = true;
    elements.resultsSummary.textContent = "Search request needs attention.";
    return;
  }

  state.results.items = payload.data.items;
  state.results.total = payload.data.pagination.total;
  state.results.totalPages = payload.data.pagination.totalPages;
  state.results.page = payload.data.pagination.page;
  state.results.latestLatencyMs = payload.meta.latencyMs;
  writeQueryState();

  await refreshSearchMetrics();
  renderSearchSummary();
  renderPagination();

  if (!state.results.items.length) {
    elements.searchResults.innerHTML = "";
    elements.searchEmptyState.hidden = false;
    return;
  }

  elements.searchEmptyState.hidden = true;
  elements.searchResults.innerHTML = state.results.items
    .map(
      (slot) => `
        <article class="result-card" data-provider-id="${slot.provider_id}" data-slot-id="${slot.id}">
          <button type="button" class="result-card__body" data-action="provider" data-provider-id="${slot.provider_id}" data-slot-id="${slot.id}" aria-label="View provider details for ${slot.provider_name}">
            <div class="result-card__eyebrow">${slot.specialty}</div>
            <h3>${slot.provider_name}</h3>
            <p>${slot.appointment_date} | ${slot.start_time} - ${slot.end_time}</p>
            <p>${slot.location}</p>
          </button>
          <div class="result-card__footer">
            <span class="result-card__meta">${slot.duration_minutes} min</span>
            <div class="card-actions">
              <button type="button" class="ghost-btn" data-action="provider" data-provider-id="${slot.provider_id}" data-slot-id="${slot.id}">Provider details</button>
              <button type="button" data-action="book" data-slot-id="${slot.id}">Book Now</button>
            </div>
          </div>
        </article>
      `,
    )
    .join("");

  elements.searchResults.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const slotId = Number(button.getAttribute("data-slot-id"));
      if (button.getAttribute("data-action") === "provider") {
        const providerId = Number(button.getAttribute("data-provider-id"));
        await showProviderDetails(providerId, slotId);
        return;
      }
      await jumpToBooking(slotId);
    });
  });
}

async function refreshSearchMetrics() {
  const payload = await fetchJson("/api/metrics/search");
  if (payload.success) {
    state.results.metrics = payload.data;
  }
}

function renderSearchSummary() {
  const startIndex = state.results.total === 0 ? 0 : (state.results.page - 1) * state.results.pageSize + 1;
  const endIndex = Math.min(state.results.total, state.results.page * state.results.pageSize);
  elements.resultsSummary.textContent = state.results.total
    ? `Showing ${startIndex}-${endIndex} of ${state.results.total} available slots.`
    : "No slots available for the current filters.";

  if (!state.results.metrics) {
    elements.searchMetricsSummary.textContent = `Latest query ${state.results.latestLatencyMs}ms`;
    return;
  }

  const alertSuffix = state.results.metrics.alertBreached ? " Latency alert is currently breached." : "";
  elements.searchMetricsSummary.textContent = `Latest query ${state.results.latestLatencyMs}ms. P95 ${state.results.metrics.p95LatencyMs}ms, empty rate ${state.results.metrics.emptyResultRate}%.${alertSuffix}`;
}

function renderPagination() {
  elements.paginationLabel.textContent = `Page ${state.results.page} of ${state.results.totalPages}`;
  elements.previousPageButton.disabled = state.results.page <= 1;
  elements.nextPageButton.disabled = state.results.page >= state.results.totalPages;
}

function changePage(direction) {
  const nextPage = state.results.page + direction;
  if (nextPage < 1 || nextPage > state.results.totalPages) {
    return;
  }
  state.results.page = nextPage;
  writeQueryState();
  Promise.all([renderSearchResults(), renderCalendar()]);
}

function expandDateRange() {
  const today = new Date().toISOString().slice(0, 10);
  if (!state.filters.dateFrom) {
    state.filters.dateFrom = today;
  }
  const base = state.filters.dateTo || state.filters.dateFrom || today;
  const date = new Date(base);
  date.setDate(date.getDate() + 7);
  state.filters.dateTo = date.toISOString().slice(0, 10);
  applyFilterInputs();
  state.results.page = 1;
  writeQueryState();
  Promise.all([renderSearchResults(), renderCalendar()]);
}

async function jumpToBooking(slotId) {
  await selectSlot(slotId);
  document.getElementById("selectionTitle").scrollIntoView({ behavior: "smooth", block: "start" });
  elements.reserveSlotButton.focus();
}

async function renderCalendar() {
  renderFilterSummary();
  const params = new URLSearchParams({
    ...state.filters,
    view: state.calendar.view,
    anchorDate: state.calendar.anchorDate,
  });
  const payload = await fetchJson(`/api/appointments/calendar?${params.toString()}`);
  if (!payload.success) {
    elements.calendarGrid.innerHTML = `<div class="calendar-empty">${payload.error.message}</div>`;
    return;
  }
  const data = payload.data;
  state.calendar.anchorDate = data.anchorDate;
  elements.calendarRangeLabel.textContent = `${data.rangeStart} to ${data.rangeEnd}`;
  elements.timezoneLabel.textContent = data.timezone;
  elements.calendarFootnote.textContent = data.utcFooter;
  elements.monthViewButton.classList.toggle("is-active", state.calendar.view === "month");
  elements.weekViewButton.classList.toggle("is-active", state.calendar.view === "week");

  const fragment = document.createDocumentFragment();
  data.days.forEach((day) => {
    const article = document.createElement("article");
    article.className = `calendar-day ${day.isCurrentMonth ? "" : "calendar-day--muted"}`;
    const slotsMarkup = day.slots.length
      ? day.slots
          .map((slot) => {
            const tone = slot.status === "available" ? "slot-pill--available" : "slot-pill--booked";
            return `
              <button
                type="button"
                class="slot-pill ${tone}"
                data-slot-id="${slot.id}"
                aria-label="${slot.provider_name} on ${slot.appointment_date} at ${slot.start_time}"
              >
                ${slot.start_time}
              </button>
            `;
          })
          .join("")
      : '<div class="slot-empty">No slots</div>';
    article.innerHTML = `
      <header>
        <span class="calendar-day__label">${day.dayLabel}</span>
        <strong>${day.dayNumber}</strong>
      </header>
      <div class="calendar-slots">${slotsMarkup}</div>
    `;
    fragment.appendChild(article);
  });
  elements.calendarGrid.innerHTML = "";
  elements.calendarGrid.appendChild(fragment);
  document.querySelectorAll(".slot-pill").forEach((button) => {
    button.addEventListener("click", async () => {
      const slotId = Number(button.getAttribute("data-slot-id"));
      await selectSlot(slotId);
    });
  });
}

async function selectSlot(slotId) {
  const payload = await fetchJson(`/api/appointments/${slotId}`);
  if (!payload.success) return;
  state.selectedSlot = payload.data;
  renderSelectedSlot();
  renderBookingSummary();
  await populatePreferredSlots();
}

function renderSelectedSlot() {
  const slot = state.selectedSlot;
  if (!slot) {
    elements.selectedSlotDetails.textContent = "Select a slot from the calendar to view provider details, location, duration, and reserve it for checkout.";
    return;
  }
  const responsiveImage = buildResponsiveImage(slot);
  elements.selectedSlotDetails.innerHTML = `
    <article class="provider-card">
      ${responsiveImage}
      <div>
        <h3>${slot.provider_name}</h3>
        <p><strong>${slot.specialty}</strong> | ${slot.credentials}</p>
        <p>${slot.appointment_date} at ${slot.start_time} - ${slot.end_time}</p>
        <p>${slot.location} | ${slot.duration_minutes} minutes</p>
        <p>${slot.bio || ""}</p>
        <div class="card-actions">
          <button type="button" class="ghost-btn" id="viewProviderDetailsButton">Provider details</button>
        </div>
      </div>
    </article>
  `;
  document.getElementById("viewProviderDetailsButton").addEventListener("click", showProviderDetails);
}

function buildResponsiveImage(slot) {
  if (!slot.photo_url) {
    return "";
  }
  return `
    <img
      class="provider-photo"
      src="${slot.photo_url}"
      srcset="${slot.photo_url}&w=320 320w, ${slot.photo_url}&w=640 640w"
      sizes="(max-width: 767px) 100vw, 320px"
      alt="Portrait of ${slot.provider_name}"
      loading="lazy"
      width="160"
      height="160"
    />
  `;
}

async function showProviderDetails(providerId = state.selectedSlot?.provider_id, slotId = state.selectedSlot?.id) {
  if (!providerId) return;
  if (slotId && (!state.selectedSlot || state.selectedSlot.id !== slotId)) {
    await selectSlot(slotId);
  }
  const payload = await fetchJson(`/api/providers/${providerId}`);
  if (!payload.success) return;
  const provider = payload.data;
  elements.providerDialogBody.innerHTML = `
    <p><strong>${provider.name}</strong></p>
    <p>${provider.specialty} | ${provider.credentials}</p>
    <p>${provider.bio || ""}</p>
    <p>Reviews: ${provider.review_count}</p>
  `;
  elements.providerDialog.showModal();
}

async function populatePreferredSlots() {
  if (!state.selectedSlot) return;
  const params = new URLSearchParams({ specialty: state.selectedSlot.specialty, provider: state.selectedSlot.provider_name, pageSize: "20" });
  const payload = await fetchJson(`/api/appointments/search?${params.toString()}`);
  elements.preferredSlotId.innerHTML = '<option value="">No preferred slot</option>';
  if (!payload.success) return;
  payload.data.items
    .filter((item) => item.id !== state.selectedSlot.id)
    .slice(0, 8)
    .forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = `${item.appointment_date} ${item.start_time} - ${item.location}`;
      elements.preferredSlotId.appendChild(option);
    });
}

function renderBookingSummary() {
  if (!state.selectedSlot) {
    elements.bookingSummary.textContent = "Choose a slot to populate your final summary.";
    return;
  }
  elements.bookingSummary.innerHTML = `
    <p><strong>Provider:</strong> ${state.selectedSlot.provider_name}</p>
    <p><strong>Specialty:</strong> ${state.selectedSlot.specialty}</p>
    <p><strong>Date:</strong> ${state.selectedSlot.appointment_date}</p>
    <p><strong>Time:</strong> ${state.selectedSlot.start_time} - ${state.selectedSlot.end_time}</p>
    <p><strong>Location:</strong> ${state.selectedSlot.location}</p>
    <p><strong>Duration:</strong> ${state.selectedSlot.duration_minutes} minutes</p>
  `;
}

async function reserveSelectedSlot() {
  if (!state.selectedSlot) {
    elements.checkoutStatusMessage.textContent = "Select a slot before reserving it.";
    return;
  }
  const payload = {
    idempotencyKey: crypto.randomUUID(),
    preferredSlotId: elements.preferredSlotId.value || null,
  };
  const response = await postJson(`/api/appointments/${state.selectedSlot.id}/checkout`, payload);
  if (!response.success) {
    elements.checkoutStatusMessage.textContent = response.error.message;
    return;
  }
  state.reservationToken = response.data.reservationToken;
  state.reservationExpiresAt = response.data.expiresAt;
  elements.checkoutStatusMessage.textContent = "Slot reserved for 60 seconds. Complete checkout below.";
  startReservationCountdown();
}

function startReservationCountdown() {
  clearInterval(state.reservationTimerId);
  state.reservationTimerId = setInterval(() => {
    const secondsRemaining = Math.max(0, Math.floor((new Date(state.reservationExpiresAt) - new Date()) / 1000));
    elements.reservationCountdown.textContent = secondsRemaining > 0 ? `Reservation expires in ${secondsRemaining}s` : "Reservation expired";
    if (secondsRemaining <= 0) {
      clearInterval(state.reservationTimerId);
      state.reservationToken = "";
    }
  }, 1000);
}

function validateCheckoutForm() {
  const requiredFields = [
    ["firstName", "First name is required."],
    ["lastName", "Last name is required."],
    ["email", "Email is required."],
    ["phone", "Phone is required."],
  ];
  let valid = true;
  requiredFields.forEach(([fieldId, message]) => {
    const field = document.getElementById(fieldId);
    const error = document.getElementById(`${fieldId}Error`);
    if (!field.value.trim()) {
      error.textContent = message;
      field.setAttribute("aria-invalid", "true");
      valid = false;
    } else {
      error.textContent = "";
      field.removeAttribute("aria-invalid");
    }
  });
  return valid;
}

async function onBookNow(event) {
  event.preventDefault();
  if (!validateCheckoutForm()) {
    elements.checkoutStatusMessage.textContent = "Please fix the inline validation errors before booking.";
    return;
  }
  if (!state.reservationToken) {
    elements.checkoutStatusMessage.textContent = "Reserve a slot first so the 60-second checkout lock is active.";
    return;
  }
  const payload = {
    reservationToken: state.reservationToken,
    idempotencyKey: crypto.randomUUID(),
    firstName: document.getElementById("firstName").value.trim(),
    lastName: document.getElementById("lastName").value.trim(),
    email: document.getElementById("email").value.trim(),
    phone: document.getElementById("phone").value.trim(),
    timezone: document.getElementById("timezone").value.trim(),
    notes: document.getElementById("notes").value.trim(),
    preferredSlotId: elements.preferredSlotId.value || null,
    reminderChannels: Array.from(document.querySelectorAll('input[name="reminderChannel"]:checked')).map((checkbox) => checkbox.value),
  };
  const response = await postJson("/api/appointments/book", payload);
  if (!response.success) {
    elements.checkoutStatusMessage.textContent = response.error.message;
    return;
  }
  clearInterval(state.reservationTimerId);
  elements.reservationCountdown.textContent = "Booking confirmed";
  elements.checkoutStatusMessage.textContent = "Appointment booked. Processing confirmation email and calendar fan-out now.";
  await runOpsJob("/api/jobs/process-confirmations", "Confirmation delivery completed.", false);
  await runOpsJob("/api/jobs/process-calendar-sync", "Calendar sync processed.", false);
  await refreshMetrics();
  await renderCalendar();
}

async function connectProvider(provider) {
  const payload = await fetchJson(`/api/auth/${provider}/authorize`);
  if (!payload.success) return;
  const callbackResponse = await fetchJson(payload.data.authorizeUrl);
  if (callbackResponse.success) {
    state.integrations = callbackResponse.data.integration;
    renderIntegrationState();
    elements.integrationStatusMessage.textContent = callbackResponse.data.message;
    return;
  }
  elements.integrationStatusMessage.textContent = callbackResponse.error.message;
}

async function disconnectProvider(provider) {
  const response = await postJson(`/api/auth/${provider}/disconnect`, {});
  if (!response.success) return;
  state.integrations = response.data.integration;
  renderIntegrationState();
  elements.integrationStatusMessage.textContent = `${provider[0].toUpperCase() + provider.slice(1)} calendar disconnected.`;
}

async function runOpsJob(endpoint, successMessage, refresh = true) {
  const response = await postJson(endpoint, {});
  if (!response.success) {
    elements.opsStatusMessage.textContent = response.error.message;
    return;
  }
  elements.opsStatusMessage.textContent = successMessage;
  if (refresh) {
    await refreshMetrics();
  }
}

async function refreshMetrics() {
  const payload = await fetchJson("/api/dashboard/metrics");
  if (!payload.success) return;
  const blocks = Object.entries(payload.data).map(([label, values]) => {
    const body = Object.entries(values).length
      ? Object.entries(values)
          .map(([key, count]) => `<li><span>${key}</span><strong>${count}</strong></li>`)
          .join("")
      : '<li><span>No data yet</span><strong>0</strong></li>';
    return `
      <article class="ops-card">
        <h3>${label}</h3>
        <ul>${body}</ul>
      </article>
    `;
  });
  elements.dashboardMetrics.innerHTML = blocks.join("");
}

function setCalendarView(view) {
  state.calendar.view = view;
  renderCalendar();
}

function shiftCalendar(direction) {
  const anchor = new Date(state.calendar.anchorDate);
  anchor.setDate(anchor.getDate() + (state.calendar.view === "week" ? direction * 14 : direction * 28));
  state.calendar.anchorDate = anchor.toISOString().slice(0, 10);
  renderCalendar();
}

function onCalendarTouchStart(event) {
  state.calendar.touchStartX = event.changedTouches[0].clientX;
}

function onCalendarTouchEnd(event) {
  const delta = event.changedTouches[0].clientX - state.calendar.touchStartX;
  if (Math.abs(delta) < 40) return;
  shiftCalendar(delta < 0 ? 1 : -1);
}

function clearFilters() {
  state.filters = { dateFrom: "", dateTo: "", timeOfDay: "", provider: "", specialty: "", sortBy: "date", sortDir: "asc" };
  state.results.page = 1;
  applyFilterInputs();
  elements.specialty.value = "";
  clearSuggestions();
  Promise.all([renderSearchResults(), renderCalendar()]);
}

async function fetchJson(url) {
  const response = await fetch(url);
  return response.json();
}

async function postJson(url, payload, headers = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(payload),
  });
  return response.json();
}

async function loadClinicalProfile() {
  if (!elements.refreshClinicalButton) {
    return;
  }

  const payload = await fetchJson("/api/clinical/profile?patientProfileId=1");
  if (!payload.success) {
    elements.clinicalStatusMessage.textContent = "Unable to load clinical profile.";
    return;
  }

  renderClinicalProfile(payload.data);
  await loadClinicalDocuments();
  await loadThresholdConfiguration();
  await loadReviewQueue(false);
  await loadConflictQueue(false);
  elements.clinicalStatusMessage.textContent = "Clinical profile refreshed.";
}

function renderClinicalProfile(profile) {
  const medications = profile.medications || [];
  const allergies = profile.allergies || [];
  const diagnoses = profile.diagnoses || [];

  elements.overviewContent.innerHTML = `
    <div class="entity-item">
      <div class="entity-item__title">Profile summary</div>
      <div class="entity-item__meta">
        <span>Medications: ${medications.length}</span>
        <span>Allergies: ${allergies.length}</span>
        <span>Diagnoses: ${diagnoses.length}</span>
      </div>
    </div>
  `;

  elements.medicationsContent.innerHTML = renderEntityCards(medications, "No medications available.");
  elements.allergiesContent.innerHTML = renderEntityCards(allergies, "No allergies available.");
  elements.diagnosesContent.innerHTML = renderEntityCards(diagnoses, "No diagnoses available.");
}

function renderEntityCards(items, emptyText) {
  if (!items.length) {
    return `<p>${emptyText}</p>`;
  }
  return items
    .map((item) => {
      const confidence = typeof item.confidence_score === "number" ? `${Math.round(item.confidence_score * 100)}%` : "n/a";
      return `
        <article class="entity-item">
          <div class="entity-item__title">${item.entity_value || "Unknown"}</div>
          <div class="entity-item__meta">
            <span class="entity-item__confidence">${confidence}</span>
            <span>Source: ${item.source_type || "unknown"}</span>
            ${item.evidence_text ? `<span>Evidence: ${item.evidence_text}</span>` : ""}
          </div>
        </article>
      `;
    })
    .join("");
}

async function handleDocumentUpload(event) {
  event.preventDefault();

  const form = new FormData(elements.uploadDocumentForm);
  const fileName = String(form.get("fileName") || "").trim();
  const fileType = String(form.get("fileType") || "").trim().toLowerCase();
  if (!fileName || !fileType) {
    elements.uploadProgressMessage.textContent = "File name and type are required.";
    return;
  }

  const uploadPayload = await postJson("/api/documents/upload", {
    patientProfileId: 1,
    fileName,
    fileType,
  });
  if (!uploadPayload.success) {
    elements.uploadProgressMessage.textContent = uploadPayload.error?.message || "Upload failed.";
    return;
  }

  const extractPayload = await postJson("/api/clinical/extract", {
    documentId: uploadPayload.data.document_id,
  });
  if (!extractPayload.success) {
    elements.uploadProgressMessage.textContent = extractPayload.error?.message || "Extraction failed.";
    return;
  }

  elements.uploadDocumentForm.reset();
  elements.uploadProgressMessage.textContent = "Document uploaded and extracted.";
  elements.uploadDocumentDialog.close();
  await aggregateClinicalProfile();
}

async function aggregateClinicalProfile() {
  const payload = await postJson("/api/clinical/aggregate", { patientProfileId: 1 });
  if (!payload.success) {
    elements.clinicalStatusMessage.textContent = payload.error?.message || "Aggregation failed.";
    return;
  }
  renderClinicalProfile(payload.data);
  elements.clinicalStatusMessage.textContent = "Profile aggregated.";
}

async function detectClinicalConflicts() {
  const payload = await postJson("/api/clinical/detect-conflicts", { patientProfileId: 1 });
  if (!payload.success) {
    elements.clinicalStatusMessage.textContent = payload.error?.message || "Conflict detection failed.";
    return;
  }

  await loadConflictQueue();
  elements.clinicalStatusMessage.textContent = "Conflicts detected and queued for resolution.";
}

async function suggestMedicalCodes() {
  const payload = await postJson("/api/clinical/suggest-codes", { patientProfileId: 1 });
  if (!payload.success) {
    elements.clinicalStatusMessage.textContent = payload.error?.message || "Code suggestion failed.";
    return;
  }
  await loadReviewQueue(true);
  elements.clinicalStatusMessage.textContent = "Code suggestions refreshed.";
}

async function reviewCodeSuggestion(codeSuggestionId, action, overrideCode = "") {
  if (action === "override" && !overrideCode) {
    elements.clinicalStatusMessage.textContent = "Enter an override code before submitting an override.";
    return;
  }

  const payload = await postJson("/api/clinical/review-code", {
    codeSuggestionId,
    action,
    reviewerId: "clinician-1",
    rejectionReason: action === "reject" ? "Rejected from UI review queue" : null,
    overrideCode: action === "override" ? overrideCode : null,
  });
  if (!payload.success) {
    elements.clinicalStatusMessage.textContent = payload.error?.message || "Code review action failed.";
    return;
  }
  const actionLabel = action === "accept" ? "accepted" : action === "reject" ? "rejected" : "overridden";
  elements.clinicalStatusMessage.textContent = `Suggestion ${codeSuggestionId} ${actionLabel}.`;
  await loadReviewQueue();
}

async function loadThresholdConfiguration() {
  const [thresholdsPayload, icd10HistoryPayload, cptHistoryPayload] = await Promise.all([
    fetchJson("/api/clinical/thresholds"),
    fetchJson("/api/clinical/thresholds/history?codeType=icd10"),
    fetchJson("/api/clinical/thresholds/history?codeType=cpt"),
  ]);

  if (!thresholdsPayload.success) return;

  const thresholds = Object.fromEntries((thresholdsPayload.data || []).map((item) => [item.code_type, item]));
  const icd10 = thresholds.icd10?.confidence_threshold ?? 0.7;
  const cpt = thresholds.cpt?.confidence_threshold ?? 0.7;
  elements.icd10Threshold.value = String(icd10);
  elements.cptThreshold.value = String(cpt);
  elements.icd10ThresholdLabel.textContent = Number(icd10).toFixed(2);
  elements.cptThresholdLabel.textContent = Number(cpt).toFixed(2);

  const historyMarkup = [
    { label: "ICD-10", items: icd10HistoryPayload.success ? icd10HistoryPayload.data : [] },
    { label: "CPT", items: cptHistoryPayload.success ? cptHistoryPayload.data : [] },
  ]
    .map(({ label, items }) => {
      const rows = items.length
        ? items
            .map(
              (item) => `
                <div class="threshold-history-item">
                  <span>${label}: ${Number(item.old_threshold ?? 0).toFixed(2)} → ${Number(item.new_threshold).toFixed(2)}</span>
                  <span>${item.actor_id}</span>
                </div>
              `,
            )
            .join("")
        : `<div class="threshold-history-item"><span>${label}</span><span>No changes</span></div>`;
      return `<section><strong>${label}</strong>${rows}</section>`;
    })
    .join("");
  elements.thresholdHistory.innerHTML = historyMarkup;
}

function openThresholdDialog() {
  loadThresholdConfiguration();
  elements.thresholdDialog.showModal();
}

async function saveThresholdConfiguration(event) {
  event.preventDefault();
  const payloads = [
    {
      codeType: "icd10",
      confidenceThreshold: Number(elements.icd10Threshold.value),
      changeReason: elements.thresholdReason.value.trim(),
      actorId: "admin-ui",
      actorRole: "admin",
    },
    {
      codeType: "cpt",
      confidenceThreshold: Number(elements.cptThreshold.value),
      changeReason: elements.thresholdReason.value.trim(),
      actorId: "admin-ui",
      actorRole: "admin",
    },
  ];

  for (const payload of payloads) {
    const response = await postJson("/api/clinical/thresholds", payload, {
      "X-User-Id": payload.actorId,
      "X-User-Role": payload.actorRole,
    });
    if (!response.success) {
      elements.thresholdMessage.textContent = response.error?.message || "Threshold update failed.";
      return;
    }
  }

  elements.thresholdMessage.textContent = "Thresholds updated.";
  await loadThresholdConfiguration();
  await loadReviewQueue(true);
}

async function loadReviewQueue(focusTab = true) {
  const payload = await fetchJson("/api/clinical/review-queue?patientProfileId=1");
  if (!payload.success) {
    elements.codesContent.innerHTML = "<p>Unable to load review queue.</p>";
    return;
  }

  const queue = payload.data || [];
  if (!queue.length) {
    elements.codesContent.innerHTML = "<p>No review-required code suggestions.</p>";
    if (focusTab) switchClinicalTab(5);
    return;
  }

  elements.codesContent.innerHTML = queue
    .map(
      (item) => `
      <article class="code-suggestion" data-suggestion-id="${item.id}">
        <div class="code-suggestion__code">${item.code_type.toUpperCase()}: ${item.code_value}</div>
        <div>${item.code_description || "No description"}</div>
        <div class="entity-item__meta">
          <span class="entity-item__confidence">${Math.round((item.confidence_score || 0) * 100)}%</span>
          <span>Review required</span>
          <span>Evidence: ${item.evidence_text || "n/a"}</span>
        </div>
        <label class="field compact-field">
          <span>Override code</span>
          <input type="text" class="override-code-input" data-suggestion-id="${item.id}" value="${item.code_value}" />
        </label>
        <div class="code-suggestion__actions">
          <button type="button" data-action="code-accept" data-suggestion-id="${item.id}">Accept</button>
          <button type="button" class="ghost-btn" data-action="code-reject" data-suggestion-id="${item.id}">Reject</button>
          <button type="button" class="ghost-btn" data-action="code-override" data-suggestion-id="${item.id}">Override</button>
        </div>
      </article>
    `,
    )
    .join("");

  elements.codesContent.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const suggestionId = Number(button.getAttribute("data-suggestion-id"));
      const action = button.getAttribute("data-action") === "code-accept" ? "accept" : button.getAttribute("data-action") === "code-reject" ? "reject" : "override";
      const overrideInput = document.querySelector(`input.override-code-input[data-suggestion-id="${suggestionId}"]`);
      await reviewCodeSuggestion(suggestionId, action, overrideInput ? overrideInput.value.trim() : "");
    });
  });

  if (focusTab) switchClinicalTab(5);
}

async function loadConflictQueue(focusTab = true) {
  const severityFilter = elements.conflictSeverityFilter?.value || "";
  const payload = await fetchJson(`/api/clinical/conflicts?patientProfileId=1${severityFilter ? `&severity=${encodeURIComponent(severityFilter)}` : ""}`);
  if (!payload.success) {
    elements.conflictsContent.innerHTML = "<p>Unable to load unresolved conflicts.</p>";
    return;
  }

  const conflicts = payload.data || [];
  if (!conflicts.length) {
    elements.conflictsContent.innerHTML = "<p>No unresolved conflicts.</p>";
    if (focusTab) switchClinicalTab(4);
    return;
  }

  elements.conflictsContent.innerHTML = conflicts
    .map(
      (conflict) => `
      <article class="conflict-alert">
        <div class="conflict-alert__severity conflict-alert__severity--${conflict.severity}">${conflict.severity} severity</div>
        <div>${conflict.conflict_description || "Conflict detected"}</div>
        <div class="entity-item__meta">
          <span>Left: ${conflict.left_entity_value || "n/a"}</span>
          <span>Right: ${conflict.right_entity_value || "n/a"}</span>
          <span>Source: ${conflict.conflict_type}</span>
        </div>
        <div class="code-suggestion__actions">
          <button type="button" data-conflict-id="${conflict.id}" data-conflict-type="${conflict.conflict_type}">Resolve</button>
        </div>
      </article>
    `,
    )
    .join("");

  elements.conflictsContent.querySelectorAll("button[data-conflict-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const conflictId = Number(button.getAttribute("data-conflict-id"));
      const conflictType = button.getAttribute("data-conflict-type");
      const conflict = conflicts.find((item) => item.id === conflictId && item.conflict_type === conflictType);
      if (conflict) openConflictResolution(conflict);
    });
  });

  if (focusTab) switchClinicalTab(4);
}

function openConflictResolution(conflict) {
  elements.conflictResolutionForm.dataset.conflictId = String(conflict.id);
  elements.conflictResolutionForm.dataset.conflictType = conflict.conflict_type;
  elements.conflictComparison.innerHTML = renderConflictComparison(conflict);
  elements.conflictResolutionMessage.textContent = "";
  elements.conflictResolutionDialog.showModal();
}

function renderConflictComparison(conflict) {
  const leftValue = conflict.left_entity_value || "Unknown";
  const rightValue = conflict.right_entity_value || "Unknown";
  const leftDifferent = leftValue !== rightValue ? "conflict-comparison__entity--diff" : "";
  const rightDifferent = leftValue !== rightValue ? "conflict-comparison__entity--diff" : "";

  return `
    <div class="conflict-comparison__side">
      <div class="conflict-comparison__title">Left version</div>
      <div class="conflict-comparison__entity ${leftDifferent}">
        <div class="conflict-comparison__value">${leftValue}</div>
        <div class="conflict-comparison__provenance">
          <span class="conflict-comparison__badge">${conflict.left_source_type || "unknown"}</span>
          <span class="conflict-comparison__confidence">Confidence: ${Math.round((conflict.left_confidence_score || 0) * 100)}%</span>
          <span>${conflict.left_extracted_at || "n/a"}</span>
          <span>${conflict.left_evidence_text || ""}</span>
        </div>
      </div>
    </div>
    <div class="conflict-comparison__side">
      <div class="conflict-comparison__title">Right version</div>
      <div class="conflict-comparison__entity ${rightDifferent}">
        <div class="conflict-comparison__value">${rightValue}</div>
        <div class="conflict-comparison__provenance">
          <span class="conflict-comparison__badge">${conflict.right_source_type || "unknown"}</span>
          <span class="conflict-comparison__confidence">Confidence: ${Math.round((conflict.right_confidence_score || 0) * 100)}%</span>
          <span>${conflict.right_extracted_at || "n/a"}</span>
          <span>${conflict.right_evidence_text || ""}</span>
        </div>
      </div>
    </div>
  `;
}

async function submitConflictResolution(event) {
  event.preventDefault();
  const conflictId = Number(elements.conflictResolutionForm.dataset.conflictId);
  const conflictType = elements.conflictResolutionForm.dataset.conflictType;
  const action = elements.conflictAction.value;
  const selectedVersion = elements.selectedConflictVersion.value;
  const notes = elements.conflictResolutionNotes.value.trim();
  const conflictPayload = {
    conflictType,
    action,
    reviewerId: "clinician-1",
    selectedEntityId: selectedVersion,
    mergeNotes: notes,
    discardReason: action === "discard" ? notes : null,
    provenance: {
      selectedVersion,
    },
  };

  const response = await postJson(`/api/conflicts/${conflictId}/resolve`, conflictPayload);
  if (!response.success) {
    elements.conflictResolutionMessage.textContent = response.error?.message || "Conflict resolution failed.";
    return;
  }

  elements.conflictResolutionForm.reset();
  elements.conflictResolutionDialog.close();
  elements.conflictResolutionMessage.textContent = "Conflict resolved.";
  await loadConflictQueue();
}

async function loadClinicalDocuments() {
  const payload = await fetchJson("/api/clinical/documents?patientProfileId=1");
  if (!payload.success) {
    return;
  }
  const documents = payload.data || [];
  if (!documents.length) {
    elements.documentsContent.innerHTML = "<p>No uploaded documents.</p>";
    return;
  }

  elements.documentsContent.innerHTML = documents
    .map(
      (doc) => `
      <article class="document-item">
        <div class="document-item__name">${doc.file_name}</div>
        <div class="entity-item__meta">
          <span class="document-item__status">${doc.upload_status}</span>
          <span>${doc.file_type.toUpperCase()}</span>
          <span>${doc.upload_timestamp}</span>
        </div>
      </article>
    `,
    )
    .join("");
}

function switchClinicalTab(index) {
  elements.clinicalTabs.forEach((tab, tabIndex) => {
    tab.classList.toggle("is-active", tabIndex === index);
    tab.setAttribute("aria-selected", tabIndex === index ? "true" : "false");
  });
  elements.clinicalTabPanels.forEach((panel, panelIndex) => {
    panel.hidden = panelIndex !== index;
  });
}
