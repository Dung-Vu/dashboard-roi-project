const DEFAULT_DATE_FROM = "2026-01-01";

const currencyFormatter = new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
});

const percentFormatter = new Intl.NumberFormat("vi-VN", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
});

const numberFormatter = new Intl.NumberFormat("vi-VN");

const state = {
    projects: [],
    query: "",
    loading: false,
};

const elements = {
    statusText: document.getElementById("statusText"),
    fetchedAt: document.getElementById("fetchedAt"),
    refreshButton: document.getElementById("refreshButton"),
    searchInput: document.getElementById("searchInput"),
    totalBgValue: document.getElementById("totalBgValue"),
    totalCostValue: document.getElementById("totalCostValue"),
    weightedGpValue: document.getElementById("weightedGpValue"),
    validProjectValue: document.getElementById("validProjectValue"),
    projectTableBody: document.getElementById("projectTableBody"),
    emptyState: document.getElementById("emptyState"),
    tagBuckets: document.getElementById("tagBuckets"),
    tagRanks: document.getElementById("tagRanks"),
};

function formatMoney(value) {
    return currencyFormatter.format(Number(value || 0));
}

function formatPercent(value) {
    if (value === null || value === undefined) {
        return "-";
    }
    return `${percentFormatter.format(Number(value || 0))}%`;
}

function formatDate(value) {
    if (!value) {
        return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return new Intl.DateTimeFormat("vi-VN", {
        dateStyle: "short",
        timeStyle: "short",
    }).format(date);
}

function normalize(value) {
    return String(value || "").toLocaleLowerCase("vi-VN");
}

function projectMatchesQuery(project) {
    const query = normalize(state.query);
    if (!query) {
        return true;
    }
    return [
        project.project_name,
        project.sale_order_name,
        project.customer,
        ...(project.tags || []),
    ].some((value) => normalize(value).includes(query));
}

function renderSummary(summary) {
    elements.totalBgValue.textContent = formatMoney(summary.total_bg_untaxed);
    elements.totalCostValue.textContent = formatMoney(summary.total_native_expected_cost);
    elements.weightedGpValue.textContent = formatPercent(summary.weighted_gp_percent);
    elements.validProjectValue.textContent = numberFormatter.format(summary.valid_project_count || 0);
}

function renderProjects() {
    const visibleProjects = state.projects.filter(projectMatchesQuery);
    elements.projectTableBody.innerHTML = visibleProjects
        .map((project) => {
            const tagText = (project.tags || []).join(", ") || "-";
            const gpClass = Number(project.gp_percent || 0) < 0 ? "negative" : "";
            return `
                <tr>
                    <td>
                        <strong>${escapeHtml(project.project_name || "-")}</strong>
                        <span>${escapeHtml(project.sale_order_name || "-")} · ${escapeHtml(project.customer || "-")}</span>
                        <small>${escapeHtml(tagText)}</small>
                    </td>
                    <td>${formatMoney(project.bg_untaxed)}</td>
                    <td>${formatMoney(project.native_expected_cost)}</td>
                    <td class="${gpClass}">
                        <strong>${formatPercent(project.gp_percent)}</strong>
                        <span>${formatMoney(project.gp_amount)}</span>
                    </td>
                </tr>
            `;
        })
        .join("");
    elements.emptyState.hidden = visibleProjects.length > 0;
}

function renderTagBuckets(tagBuckets) {
    elements.tagBuckets.innerHTML = Object.entries(tagBuckets || {})
        .map(([tag, tiers]) => `
            <article class="analysis-card">
                <h3>${escapeHtml(tag)}</h3>
                <div class="bucket-grid">
                    ${Object.entries(tiers)
                        .map(([tier, bucket]) => `
                            <div class="bucket-cell">
                                <span>${escapeHtml(tier)}</span>
                                <strong>${formatPercent(bucket.weighted_gp_percent)}</strong>
                                <small>${numberFormatter.format(bucket.count || 0)} project · ${formatMoney(bucket.bg_untaxed)}</small>
                            </div>
                        `)
                        .join("")}
                </div>
            </article>
        `)
        .join("");
}

function renderTagRanks(tagRanks) {
    elements.tagRanks.innerHTML = Object.entries(tagRanks || {})
        .map(([tag, ranks]) => `
            <article class="analysis-card">
                <h3>${escapeHtml(tag)}</h3>
                <div class="rank-list">
                    ${(ranks.length ? ranks : [{ rank: "-", range: "-", count: 0, bg_untaxed: 0 }])
                        .map((rank) => `
                            <div class="rank-row">
                                <span>#${rank.rank}</span>
                                <strong>${escapeHtml(rank.range)}</strong>
                                <small>${numberFormatter.format(rank.count || 0)} project · ${formatMoney(rank.bg_untaxed)}</small>
                            </div>
                        `)
                        .join("")}
                </div>
            </article>
        `)
        .join("");
}

function renderDashboard(data) {
    state.projects = data.projects || [];
    renderSummary(data.summary || {});
    renderProjects();
    renderTagBuckets(data.tag_buckets || {});
    renderTagRanks(data.tag_gp_ranks || {});
    elements.fetchedAt.textContent = formatDate(data.fetched_at);
    elements.statusText.textContent = `${numberFormatter.format(state.projects.length)} project từ ${data.date_from || DEFAULT_DATE_FROM}`;
}

function setLoading(isLoading) {
    state.loading = isLoading;
    elements.refreshButton.disabled = isLoading;
    elements.statusText.textContent = isLoading ? "Đang tải toàn bộ project..." : elements.statusText.textContent;
}

async function loadDashboard({ refresh = false } = {}) {
    setLoading(true);
    try {
        const params = new URLSearchParams({ date_from: DEFAULT_DATE_FROM });
        if (refresh) {
            params.set("refresh", "1");
        }
        const response = await fetch(`/api/projects-dashboard?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Không tải được dashboard");
        }
        renderDashboard(payload);
    } catch (error) {
        elements.statusText.textContent = error.message;
        window.alert(error.message);
    } finally {
        setLoading(false);
    }
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

elements.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value;
    renderProjects();
});

elements.refreshButton.addEventListener("click", () => {
    loadDashboard({ refresh: true });
});

loadDashboard();
