# Project: Bonario ROI Dashboard - Aura Forest Theme 2.0 Big Update

## Architecture
Bonario ROI Dashboard is a Single Page Application (SPA) that displays Gross Profit (GP) and return on investment analytics.
The front-end consists of:
- `index.html`: Holds the structure, routing sections, static UI panels, and background container.
- `app.js`: Contains state, logic, DOM rendering, Chart.js integrations, and API interaction (ESM).
- `styles.css`: Visual appearance following premium biophilic design guidelines with modern glassmorphism.

The Phase 2 Big Update introduces premium biophilic visual upgrades:
1. **Dynamic Background**: 4 orbital CSS keyframe glow orbs + GPU-optimized floating bio-particles.
2. **Sparklines in KPI**: SVG trend curves inline within KPI cards for GP% trend tracking.
3. **Glowing health orbs**: Column "Sức khỏe ROI" in projects list with frosted glass pulsing bubbles.
4. **Dual-Column Ranks page**: REST API data displayed in 2-column layout (GP% bar chart, Revenue share doughnut chart, Tag Performance Leaderboard with gold-leaf accenting).
5. **Sidebar Slide Indicator**: Vertical glass slide-active indicator following hash routing.

```
+-------------------------------------------------------------+
|                        Browser DOM                          |
|  +-------------------------------------------------------+  |
|  | Ambient BG (4 Glow Orbs + Biophilic Floating Particles)|  |
|  +-------------------------------------------------------+  |
|  | Sidebar (frosted indicator `.menu-indicator` sliding)  |  |
|  +-------------------------------------------------------+  |
|  | KPI Grid with Moss-to-Emerald SVG Sparklines           |  |
|  +-------------------------------------------------------+  |
|  | Projects Table with pulsing Frosted Health Orbs       |  |
|  +-------------------------------------------------------+  |
|  | Ranks Route (Left: Bar Chart, Right: Doughnut + Ldb)  |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
                               ^
                               | DOM updates using DocumentFragment
+-------------------------------------------------------------+
|                      app.js (ESM)                           |
|  +-------------------------------------------------------+  |
|  | State (dashboardData, filteredProjects, charts)       |  |
|  +-------------------------------------------------------+  |
|  | Render Methods (including Sparkline, Doughnut, Orbs)  |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
                               ^
                               | HTTP Fetch JSON
+-------------------------------------------------------------+
|                      Flask backend                          |
+-------------------------------------------------------------+
```

## Milestones

### Phase 1: Core Performance & Security (Completed)
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | ESM Module Integration | Restructure app.js variables and events as an ES Module, set script type="module" in index.html. | None | DONE |
| M2 | Security Sanitization | escapeHTML helper mapping dynamic inputs before rendering to prevent XSS payloads. | M1 | DONE |
| M3 | Performance Optimization | DocumentFragment usage in renderProjectsTable and renderTagAnalysis for single DOM reflows. | M2 | DONE |

### Phase 2: Aura Forest Theme 2.0 Big Update (Current)
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M4 | Dynamic Biophilic BG | 4 glowing ambient orbs with free-flowing orbital paths + CPU-friendly biophilic floating particles. | M3 | DONE |
| M5 | KPI SVG Sparklines | Dynamic inline SVG curves representing historical GP% trend of last 10 projects. | M3 | DONE |
| M6 | Glowing Health Orbs | Frosted glass health indicator bubbles pulsing under new column "Sức khỏe ROI". | M3 | DONE |
| M7 | Professional Ranks Page | 2-column layout dividing Sage-Mint-Emerald Bar Chart, Doughnut chart, and Gold-Leaf Tag Leaderboard. | M3 | DONE |
| M8 | Sidebar Active Indicator | `.menu-indicator` vertical tracking slider utilizing cubic-bezier smooth transition. | M3 | DONE |
| M9 | E2E Testing & Hardening | Opaque-box requirements verification and white-box challenger hardening. | M4-M8 | DONE |

## Interface Contracts
- `escapeHTML(str: string): string` - Safely escapes HTML special characters.
- `renderProjectsTable(projects: Array<Project>): void` - Renders the project list dynamically using a single `DocumentFragment` write, including "Sức khỏe ROI" glowing bubble indicator.
- `renderTagAnalysis(tagBuckets: Object, tagGPRanks: Object): void` - Renders tag contribution analysis.
- `renderKPIs(summary: Object, projects: Array<Project>): void` - Renders total metric fields and updates embedded inline SVG sparklines representing trending GP%.
- `renderGPChart(tagGPRanks: Object): void` - Renders GP% distribution chart using professional gradient fills.
- `renderTagDoughnutChart(projects: Array<Project>): void` - Renders doughnut chart showing revenue contribution per tag category.
- `renderTagLeaderboard(projects: Array<Project>): void` - Renders top performing tags with gold-leaf styled score ranks.
- `updateSidebarIndicator(activeHash: string): void` - Sets offset transition for sidebar hover indicator.

## Code Layout
- `/index.html`: Main HTML entry-point.
- `/app.js`: ES6 client module containing routing, state, dynamic rendering, and visual bindings.
- `/styles.css`: Stylesheet defining layouts, colors, glassmorphism, indicators, and biometric particle animations.
