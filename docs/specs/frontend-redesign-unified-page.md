# Feature Spec: Frontend Redesign — Unified Single-Page Experience

**Author**: Planner + Tech Advisor Agent
**Date**: 2026-02-16
**Status**: Draft — Awaiting Approval
**Phase**: 4 (Enhanced UX)

---

## Problem

EquiTable currently has two disconnected pages: a dark-themed landing page (`/`) with marketing content and a light-themed map page (`/map`) with all interactive functionality. Users must click through from landing → map, which creates a jarring context switch (dark → light, scroll → fixed, marketing → product). This pattern feels dated and hides the product's core value — the live map — behind a click.

Modern product sites (Protent.ai, Linear, Vercel) embed interactive product demos within the scroll flow, letting users experience the product before committing to a full-screen interaction. The current two-page split also hurts SEO (all product content lives on `/map`, invisible to crawlers on `/`) and reduces engagement (users who don't click "Launch System" never see the map).

## Proposed Solution

Merge the landing page and map page into a **single continuous scroll experience** with an **expandable map overlay**:

1. **Hero** — Keep existing animated hero with gradient orbs (dark theme)
2. **Mission / How It Works** — Keep existing sections (dark theme)
3. **Map Preview** — Embedded, interactive Google Maps widget (~60vh) showing nearby pantries within the scroll flow. This is a real, live map with markers — not a screenshot. Uses a dark-to-light gradient transition at the section boundary.
4. **Map Expand** — A "View Full Map" button / expand icon on the map preview triggers a **full-screen overlay** that contains the complete map experience (sidebar, filters, detail panel, geolocation, radius slider). This uses Framer Motion `layoutId` animation for a smooth expand, not a page navigation.
5. **Stats / Social Proof** — Below the map preview section (dark theme)
6. **Footer with CTA**

The `/map` route still works for direct URL access and sharing — it renders the page with the map overlay already expanded on mount.

### Key UX Patterns

- **Scroll-embedded product demo**: The map preview section is interactive (pan, zoom, click markers) but contained within the scroll flow. This follows the Protent.ai pattern of "try before you commit."
- **Smooth expand transition**: Clicking "View Full Map" expands the map from its inline container to fill the viewport using Framer Motion `layout` animation (~400ms, spring physics). The sidebar/filters slide in after the map expansion completes.
- **Collapse back to scroll**: An "X" or "Back" button in the full-screen overlay collapses the map back to its inline position. Scroll position is preserved.
- **Dark → Light boundary**: The map preview section uses a gradient transition from the dark landing theme to the light map theme, creating visual continuity.

---

## API Contract

**No API changes required.** All existing endpoints are consumed as-is:

| Endpoint | Usage | Changed? |
|----------|-------|----------|
| `GET /pantries?city=&state=` | Map preview + full map | No |
| `GET /pantries/nearby` | Radius filter in full map | No |
| `GET /cities` | City dropdown + stats | No |

---

## Database Changes

**None.** This is a pure frontend restructure.

---

## Component Tree

```
App.jsx
├── Route "/" → UnifiedPage.jsx (NEW — replaces LandingPage)
│   ├── GridBackground (existing, moved)
│   ├── HeroSection (existing, moved)
│   ├── MissionSection (existing, moved)
│   ├── HowItWorksSection (existing, moved)
│   ├── MapPreviewSection (NEW)
│   │   ├── DarkToLightGradient (NEW — CSS gradient bridge)
│   │   ├── PantryMapClean (existing — preview mode, reduced props)
│   │   │   ├── Markers (existing)
│   │   │   └── InfoWindow (existing)
│   │   └── ExpandMapButton (NEW)
│   ├── StatsSection (existing, moved)
│   ├── TerminalSection (existing, moved)
│   ├── FinalCTASection (existing, modified — CTA opens map overlay)
│   ├── Footer (existing, moved)
│   └── MapOverlay (NEW — full-screen map experience)
│       ├── OverlayHeader (NEW — close button, breadcrumb)
│       └── MapExperience (NEW — extracted from MapPage)
│           ├── Sidebar (existing logic from MapPage)
│           │   ├── CityDropdown (existing)
│           │   ├── RadiusSlider (existing)
│           │   ├── SearchInput (existing)
│           │   ├── FilterChips (existing)
│           │   └── PantryList (existing)
│           ├── PantryMapClean (existing — full mode)
│           ├── PantryDetailPanel (existing)
│           ├── NearMeButton (existing)
│           └── Legend (existing)
├── Route "/map" → UnifiedPage.jsx (same component, with ?expand=true)
└── Route "*" → Navigate to "/"
```

### New Components

| Component | Owner | Description |
|-----------|-------|-------------|
| `UnifiedPage.jsx` | Frontend Data Agent | New page component replacing both LandingPage and MapPage. Manages map expanded/collapsed state, scroll position, lazy loading. |
| `MapPreviewSection.jsx` | Frontend UI Agent | Scroll section containing the inline map preview with expand button and dark-to-light gradient transition. |
| `MapOverlay.jsx` | Frontend UI Agent | Full-screen overlay containing the complete map experience. Framer Motion `AnimatePresence` for enter/exit. |
| `MapExperience.jsx` | Frontend Data Agent | Extracted map logic from MapPage (all hooks, state, data fetching). Receives `isPreview` prop to control behavior. |
| `ExpandMapButton.jsx` | Frontend UI Agent | Floating button on map preview — "Explore Full Map" with expand icon. |

### Existing Components (Unchanged)

All landing page sections (`HeroSection`, `MissionSection`, `HowItWorksSection`, `StatsSection`, `TerminalSection`, `FinalCTASection`, `Footer`, `GridBackground`) move from `LandingPage.jsx` into `UnifiedPage.jsx` unchanged.

All map components (`PantryMapClean`, `CityDropdown`, `RadiusSlider`, `CitySelector`, `PantryDetailPanel`) are used as-is inside `MapExperience`.

### Modified Components

| Component | Change |
|-----------|--------|
| `App.jsx` | Replace two routes with unified routing. `/map` renders `UnifiedPage` with `expandMap=true` search param. |
| `FinalCTASection` | CTA button opens map overlay instead of linking to `/map`. Accepts `onOpenMap` callback prop. |
| `PantryMapClean` | Add optional `interactive` prop (default `true`). In preview mode, set `gestureHandling="cooperative"` instead of `"greedy"` so scroll passes through to the page. |

---

## Data Flow

### Flow 1: User scrolls to map preview (lazy load)

1. User scrolls down the unified page
2. `MapPreviewSection` enters viewport → `IntersectionObserver` fires
3. `APIProvider` (Google Maps) loads for the first time (lazy)
4. `usePantries()` or `useCities()` fetches initial data
5. Map renders with markers in the preview container (~60vh)
6. User can pan/zoom/click markers in the preview

### Flow 2: User expands to full map

1. User clicks "Explore Full Map" button on preview section
2. `setMapExpanded(true)` → URL updates to `?expand=true` via `useSearchParams`
3. `MapOverlay` mounts with Framer Motion `AnimatePresence`
4. Overlay animates in: backdrop fades (200ms), map container scales from preview position to full viewport (400ms spring)
5. After animation, sidebar slides in from left (200ms)
6. Body scroll is locked (`overflow: hidden` on `<html>`)
7. All existing map functionality is available (city dropdown, radius, search, filters, detail panel, geolocation)

### Flow 3: User collapses back to scroll

1. User clicks close button in overlay header
2. `setMapExpanded(false)` → `?expand=true` removed from URL
3. Overlay animates out: sidebar slides out (150ms), map shrinks back (300ms spring), backdrop fades (200ms)
4. Body scroll unlocked, restored to previous scroll position
5. Map preview section is still visible and interactive

### Flow 4: Direct URL to /map

1. User navigates to `/map` (shared link, bookmark)
2. `UnifiedPage` mounts, detects `/map` route
3. `mapExpanded` initialized to `true` (skip scroll, show overlay immediately)
4. Full map experience is visible on load (same as if user expanded from preview)
5. Close button navigates to `/` with scroll position at map preview section

### Flow 5: Mobile behavior

1. Map preview section is ~50vh on mobile
2. "Explore Full Map" button is more prominent (full-width)
3. Full-screen overlay is 100vh with sidebar as bottom sheet (existing behavior)
4. Close button is in top-left corner of overlay
5. iOS safe area insets are respected via `env(safe-area-inset-*)`

---

## Technology Decisions

### Lazy Loading: Intersection Observer API

**Chosen**: Native `IntersectionObserver` via a `useInView` hook (custom or from Framer Motion's `useInView`)

**Alternatives considered**:
1. **React.lazy + Suspense** — Lazy loads the component JS chunk but doesn't control when Google Maps API loads. Also, Suspense boundaries don't work well with map initialization.
2. **Third-party library (react-intersection-observer)** — Adds a dependency for something achievable in ~10 lines with native API or already included in Framer Motion.

**Why IntersectionObserver wins**: We need to control when the `<APIProvider>` mounts (which triggers Google Maps JS download). Framer Motion's `useInView` is already available and returns a boolean we can use for conditional rendering. Zero new dependencies.

### Map Expand Animation: Framer Motion layout animation

**Chosen**: Framer Motion `AnimatePresence` + `motion.div` with enter/exit variants

**Alternatives considered**:
1. **Framer Motion `layoutId`** — Shares layout between preview map and overlay map. Elegant but problematic: two Google Maps instances would need to sync state, or one map would need to be re-parented in the DOM. Re-parenting causes the map to re-initialize (flash).
2. **CSS View Transitions API** — Experimental, limited browser support, and difficult to coordinate with React state.

**Why AnimatePresence wins**: Simpler mental model — the overlay is a separate layer that animates in/out. The preview map stays in the DOM underneath (hidden by the overlay). When the overlay closes, the preview map is already there. No re-initialization, no state sync. The trade-off is two map instances briefly exist, but only one is visible.

### Scroll Lock: `body-scroll-lock` pattern

**Chosen**: Direct `document.documentElement.style.overflow = 'hidden'` with scroll position save/restore

**Alternatives considered**:
1. **body-scroll-lock library** — Handles iOS edge cases but adds a dependency for a 5-line solution.
2. **CSS `overscroll-behavior`** — Doesn't actually prevent scroll on the body.

**Why direct style manipulation wins**: Simple, no dependency, handles the common case. If iOS bugs appear later, we add the library then.

### Route Strategy: Single route with search param

**Chosen**: `/` is the unified page. `/map` is an alias that renders the same component with `expand=true`. Search params control overlay state.

**Alternatives considered**:
1. **Keep separate routes** — Defeats the purpose of the redesign.
2. **Hash-based routing (`/#map`)** — Less clean, doesn't work well with React Router.

**Why search param wins**: Clean URLs (`/` and `/map`), easy to share (`/map` always opens full map), backward compatible (existing `/map` links still work), and React Router's `useSearchParams` is already in use.

---

## Detailed Implementation Notes

### Dark-to-Light Gradient Bridge

The landing page uses a dark theme (`bg-zinc-950`), and the map uses a light theme. The `MapPreviewSection` bridges this with:

```jsx
{/* Above map: dark → transparent gradient */}
<div className="h-32 bg-gradient-to-b from-zinc-950 to-transparent relative z-10" />

{/* Map container: light bg */}
<div className="bg-white rounded-t-3xl mx-4 lg:mx-8 overflow-hidden shadow-2xl">
  <PantryMapClean ... className="h-[60vh]" />
</div>

{/* Below map: transparent → dark gradient */}
<div className="h-32 bg-gradient-to-b from-transparent to-zinc-950 relative z-10" />
```

### Google Maps Lazy Loading

```jsx
function MapPreviewSection({ onExpand }) {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '200px' }) // preload 200px before visible

  return (
    <section ref={ref}>
      {isInView ? (
        <APIProvider apiKey={MAPS_KEY}>
          <PantryMapClean ... gestureHandling="cooperative" />
        </APIProvider>
      ) : (
        <MapPreviewSkeleton /> // Placeholder with shimmer
      )}
    </section>
  )
}
```

The `margin: '200px'` triggers loading 200px before the section scrolls into view, so the map is ready by the time the user sees it.

### Preview vs Full Map Gesture Handling

In **preview mode**, the map uses `gestureHandling="cooperative"`, which means:
- Scroll events pass through to the page (don't zoom the map)
- Two-finger pinch zooms the map
- Click and drag pans the map
- Click on marker works normally

This prevents the map from "hijacking" the scroll when the user is just scrolling past it.

In **full-screen mode**, the map uses `gestureHandling="greedy"` (current behavior) — all gestures go to the map.

### Scroll Position Save/Restore

```jsx
const scrollPosRef = useRef(0)

const handleExpandMap = () => {
  scrollPosRef.current = window.scrollY
  document.documentElement.style.overflow = 'hidden'
  setMapExpanded(true)
}

const handleCollapseMap = () => {
  setMapExpanded(false)
  document.documentElement.style.overflow = ''
  window.scrollTo(0, scrollPosRef.current)
}
```

### MapOverlay Animation Spec

```jsx
<AnimatePresence>
  {mapExpanded && (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-50 bg-white"
    >
      {/* Close button */}
      <motion.button
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2 }}
        onClick={handleCollapseMap}
        className="absolute top-4 right-4 z-[60] ..."
      >
        <X />
      </motion.button>

      {/* Map experience */}
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
        className="w-full h-full"
      >
        <MapExperience />
      </motion.div>
    </motion.div>
  )}
</AnimatePresence>
```

---

## Testing Requirements

### Frontend Test Checklist

#### New Component Tests

| Test File | Tests | Owner |
|-----------|-------|-------|
| `__tests__/UnifiedPage.test.jsx` | Renders hero section; renders map preview section; renders stats section; overlay is hidden by default; expand button triggers overlay; close button hides overlay; ESC key closes overlay | Frontend Data Agent |
| `__tests__/MapPreviewSection.test.jsx` | Renders skeleton when not in view; renders map when in view; expand button callback fires; cooperative gesture handling applied | Frontend UI Agent |
| `__tests__/MapOverlay.test.jsx` | Renders map experience when open; fires onClose callback; traps focus inside overlay; body scroll locked when open; body scroll restored on close | Frontend UI Agent |
| `__tests__/MapExperience.test.jsx` | Renders sidebar with city dropdown; renders map; search filters work; filter chips work | Frontend Data Agent |

#### Existing Tests That Must Still Pass

| Test File | Tests | Risk |
|-----------|-------|------|
| `__tests__/smoke.test.jsx` | Landing page renders; displays app name; displays tagline; has map link | **HIGH** — LandingPage component is being replaced. Smoke tests must be updated to test UnifiedPage instead. |
| `__tests__/CityDropdown.test.jsx` | All 6 tests | LOW — component unchanged |
| `__tests__/CitySelector.test.jsx` | All 6 tests | LOW — component unchanged |

#### Smoke Test Updates Required

The existing smoke tests reference `LandingPage` and check for a link to `/map`. These must be updated:

1. "renders without crashing" → Test `UnifiedPage` instead of `LandingPage`
2. "displays the app name" → Same assertion, different component
3. "displays the tagline" → Same
4. "has a link to the map page" → Change to: "has an expand map button" or "map preview section is present"
5. Add: "map overlay opens when expand button is clicked"
6. Add: "/map route renders with overlay expanded"

#### Integration Tests

| Flow | Test Description |
|------|-----------------|
| Scroll → Preview | Map preview loads when section scrolls into view |
| Preview → Full | Clicking expand shows full map overlay |
| Full → Collapse | Clicking close returns to scroll, position preserved |
| Direct /map URL | Page loads with overlay already expanded |
| Mobile | Map preview is correctly sized, overlay is full-screen |

#### Manual Verification Steps

1. Scroll through entire unified page — no layout jumps, smooth transitions
2. Map preview loads lazily (check Network tab — Google Maps JS only loads when map section approached)
3. Markers appear on preview map, clicking a marker shows InfoWindow
4. "Explore Full Map" opens overlay with smooth animation
5. All sidebar features work in overlay (city dropdown, radius slider, search, filters)
6. Close overlay — scroll position is exactly where it was
7. Navigate to `/map` directly — overlay is open, all features work
8. Mobile: map preview is ~50vh, overlay is full screen, sidebar is bottom sheet
9. Performance: Lighthouse score doesn't drop significantly (lazy loading should help)
10. Reduced motion: animations are disabled for users with `prefers-reduced-motion`

---

## Sequencing

### Step 1: Extract MapExperience from MapPage (Frontend Data Agent)

Extract all map state management, hooks, and logic from `MapPage.jsx` into a reusable `MapExperience.jsx` component. This component receives no routing-specific props — it's self-contained with all the sidebar, filters, data fetching, and detail panel logic.

**Files created/modified**:
- NEW: `frontend/src/components/MapExperience.jsx`
- MODIFIED: `frontend/src/pages/MapPage.jsx` (becomes thin wrapper around MapExperience)

**Verification**: `MapPage` still works identically at `/map`. All existing tests pass.

### Step 2: Build MapPreviewSection (Frontend UI Agent)

Build the map preview section with:
- Dark-to-light gradient bridge
- Lazy loading via `useInView`
- `PantryMapClean` in cooperative gesture mode
- Skeleton placeholder
- "Explore Full Map" expand button

**Files created**:
- NEW: `frontend/src/components/MapPreviewSection.jsx`
- NEW: `frontend/src/__tests__/MapPreviewSection.test.jsx`

**Verification**: Component renders in isolation with mock data.

### Step 3: Build MapOverlay (Frontend UI Agent)

Build the full-screen overlay with:
- Framer Motion enter/exit animations
- Close button (click + ESC key)
- Body scroll lock/unlock
- Slot for `MapExperience`

**Files created**:
- NEW: `frontend/src/components/MapOverlay.jsx`
- NEW: `frontend/src/__tests__/MapOverlay.test.jsx`

**Verification**: Overlay opens/closes with animations. Body scroll is locked when open.

### Step 4: Build UnifiedPage (Frontend Data Agent)

Assemble the unified page:
- Move all landing sections from `LandingPage.jsx`
- Add `MapPreviewSection` between HowItWorks and Stats
- Add `MapOverlay` with expand/collapse state
- Handle `/map` route (auto-expand)
- Handle search params (`?expand=true`)
- Save/restore scroll position

**Files created/modified**:
- NEW: `frontend/src/pages/UnifiedPage.jsx`
- MODIFIED: `frontend/src/App.jsx` (new routing)
- MODIFIED: `frontend/src/pages/LandingPage.jsx` (sections extracted, file may be deleted or kept as re-export)
- NEW: `frontend/src/__tests__/UnifiedPage.test.jsx`

**Verification**: Full flow works — scroll → preview → expand → use map → collapse.

### Step 5: Update Smoke Tests (Frontend Data Agent)

Update existing smoke tests to reference `UnifiedPage` instead of `LandingPage`. Add new smoke tests for map overlay behavior.

**Files modified**:
- MODIFIED: `frontend/src/__tests__/smoke.test.jsx`

**Verification**: All tests pass. `npm run build` succeeds.

### Step 6: PantryMapClean Gesture Mode (Frontend UI Agent)

Add `gestureHandling` prop to `PantryMapClean` (default `"greedy"`, preview uses `"cooperative"`).

**Files modified**:
- MODIFIED: `frontend/src/components/PantryMapClean.jsx`

**Verification**: Preview map doesn't hijack scroll. Full map works as before.

---

## Handoffs

- **Backend Agent**: No work required. Zero API changes.
- **Frontend Data Agent**: Steps 1, 4, 5 — Extract MapExperience, build UnifiedPage, update routing and smoke tests.
- **Frontend UI Agent**: Steps 2, 3, 6 — Build MapPreviewSection, MapOverlay, gesture mode prop.
- **Scraping Quality Agent**: No work required.

---

## Risks & Open Questions

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Two Google Maps instances** (preview + overlay) | Medium | Only one is visible at a time. The preview map is lightweight (no sidebar). Google Maps JS is loaded once and shared. Cost impact is minimal (map loads are not billed). |
| **Performance — landing page becomes heavier** | Medium | Lazy loading the map prevents upfront cost. Lighthouse score should be similar to current landing page until map section is scrolled to. |
| **Dark-to-light theme transition looks jarring** | Low | The gradient bridge smooths this. If it still feels abrupt, add a CSS blur/glow at the boundary. |
| **iOS scroll position restore** | Low | `window.scrollTo` is generally reliable. If iOS Safari bugs, use `scrollBehavior: 'instant'` or fall back to `element.scrollIntoView`. |
| **Existing `/map` bookmarks/links** | None | `/map` route is preserved and works as before — just opens the overlay directly. |

### Open Questions

1. **Should the map preview fetch all pantries or just a default city?** Recommendation: Fetch all pantries (no city filter) for the preview to show breadth. The full map overlay uses city/radius filters as before.
2. **Should clicking a marker in the preview auto-expand to full map?** Recommendation: No — keep the preview self-contained with InfoWindows. Users who want the full experience click "Explore Full Map."
3. **Should we keep `LandingPage.jsx` as a file?** Recommendation: Delete it and move all sections to `UnifiedPage.jsx`. Less file bloat, and the sections are already self-contained functions.

---

## ADR

This spec introduces **ADR-010: Unified Single-Page Architecture**. To be appended to `docs/decisions.md` upon approval:

```markdown
## ADR-010: Unified Single-Page Architecture

**Date**: 2026-02-16
**Status**: Accepted
**Context**: The two-page split (landing + map) created a disconnected experience.
Users had to click through to see the product. Modern product sites embed interactive
demos in the scroll flow.
**Decision**: Merge landing and map into a single scrolling page with a lazy-loaded
map preview section and a full-screen map overlay. Keep /map as a direct URL that
auto-expands the overlay.
**Consequences**: LandingPage.jsx and MapPage.jsx are replaced by UnifiedPage.jsx.
Map components are extracted into reusable MapExperience.jsx. Google Maps API is
lazy-loaded via IntersectionObserver. Two map instances briefly coexist (preview +
overlay) but only one is visible. All existing map functionality is preserved.
```
