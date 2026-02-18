import { useCallback, useRef } from 'react'

const PANTRY_THRESHOLD = 3
const DEDUP_RADIUS_KM = 2
const DEBOUNCE_MS = 1500

/**
 * Haversine distance between two lat/lng points in km.
 */
function haversineKm(a, b) {
  const R = 6371
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLng = ((b.lng - a.lng) * Math.PI) / 180
  const sinDLat = Math.sin(dLat / 2)
  const sinDLng = Math.sin(dLng / 2)
  const aVal =
    sinDLat * sinDLat +
    Math.cos((a.lat * Math.PI) / 180) *
      Math.cos((b.lat * Math.PI) / 180) *
      sinDLng * sinDLng
  return R * 2 * Math.atan2(Math.sqrt(aVal), Math.sqrt(1 - aVal))
}

/**
 * Count how many pantries fall within the given map bounds.
 */
function countPantriesInBounds(pantries, bounds) {
  const ne = bounds.getNorthEast()
  const sw = bounds.getSouthWest()
  const north = ne.lat()
  const south = sw.lat()
  const east = ne.lng()
  const west = sw.lng()

  let count = 0
  for (const p of pantries) {
    if (p.lat >= south && p.lat <= north && p.lng >= west && p.lng <= east) {
      count++
    }
  }
  return count
}

/**
 * Compute radius in km from map bounds diagonal.
 */
function boundsRadiusKm(bounds) {
  const ne = bounds.getNorthEast()
  const sw = bounds.getSouthWest()
  return haversineKm(
    { lat: ne.lat(), lng: ne.lng() },
    { lat: sw.lat(), lng: sw.lng() }
  ) / 2
}

/**
 * Hook: auto-trigger discovery when viewport has few pantries.
 *
 * @param {Object} options
 * @param {Array} options.pantries - current pantries array
 * @param {Function} options.discover - from useDiscovery
 * @param {boolean} options.isDiscovering - from useDiscovery
 * @returns {{ onMapIdle: (map) => void }}
 */
export default function useViewportDiscovery({ pantries, discover, isDiscovering }) {
  const lastCenterRef = useRef(null)
  const debounceRef = useRef(null)

  const onMapIdle = useCallback((map) => {
    // Clear any pending debounce
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }

    debounceRef.current = setTimeout(() => {
      if (isDiscovering) return

      const bounds = map.getBounds?.()
      if (!bounds) return

      const center = map.getCenter()
      if (!center) return

      const lat = center.lat()
      const lng = center.lng()

      // Dedup: skip if center hasn't moved significantly
      if (lastCenterRef.current) {
        const dist = haversineKm(lastCenterRef.current, { lat, lng })
        if (dist < DEDUP_RADIUS_KM) return
      }

      // Count pantries in current viewport
      const count = countPantriesInBounds(pantries, bounds)
      if (count >= PANTRY_THRESHOLD) return

      // Compute search radius from viewport
      const radiusKm = boundsRadiusKm(bounds)
      const radiusMeters = Math.min(Math.round(radiusKm * 1000), 50000)

      // Update last discovered center
      lastCenterRef.current = { lat, lng }

      // Trigger discovery
      discover({
        query: `food pantry`,
        lat,
        lng,
        radiusMeters,
      })
    }, DEBOUNCE_MS)
  }, [pantries, discover, isDiscovering])

  return { onMapIdle }
}
