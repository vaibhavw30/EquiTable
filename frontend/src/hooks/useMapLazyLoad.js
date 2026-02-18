import { useState, useCallback } from 'react'
import usePantries from './usePantries'

/**
 * Coordinates lazy loading of the map section with pantry data fetching.
 *
 * The visibility detection (IntersectionObserver) happens in MapPreviewSection
 * via framer-motion's useInView, which calls `onBecomeVisible()` when the
 * section enters the viewport. This avoids ref-passing timing issues.
 *
 * Returns:
 * - `isInView` — true once the section has scrolled into view (stays true)
 * - `onBecomeVisible` — callback for MapPreviewSection to call when in view
 * - `pantries` — fetched pantry data (empty until in view)
 * - `loading` — true while the initial fetch is in progress
 * - `error` — error message if fetch failed
 * - `refresh` — manually re-fetch pantries
 */
export default function useMapLazyLoad() {
  const [isInView, setIsInView] = useState(false)

  const onBecomeVisible = useCallback(() => {
    setIsInView(true)
  }, [])

  // Only fetch when in view — no city filter for preview (shows all pantries)
  const { pantries, loading, error, refresh } = usePantries({ enabled: isInView })

  return {
    isInView,
    onBecomeVisible,
    pantries,
    loading,
    error,
    refresh,
  }
}
