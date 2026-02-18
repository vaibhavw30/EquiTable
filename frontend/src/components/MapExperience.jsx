import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  Search,
  X,
  Navigation,
  ChevronLeft,
  Clock,
  Shield,
  MapPin,
  ExternalLink,
  Loader2,
  AlertTriangle,
  Menu,
  Home,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { clsx } from 'clsx'

import usePantries from '../hooks/usePantries'
import useNearbyPantries from '../hooks/useNearbyPantries'
import useCities from '../hooks/useCities'
import useDiscovery from '../hooks/useDiscovery'
import useViewportDiscovery from '../hooks/useViewportDiscovery'
import PantryMapClean from './PantryMapClean'
import DiscoveryOverlay from './DiscoveryOverlay'
import CitySelector from './CitySelector'
import CityDropdown from './CityDropdown'
import RadiusSlider, { milesToMeters, radiusToZoom } from './RadiusSlider'

// Google Maps directions URL
function directionsUrl(pantry) {
  const destination = encodeURIComponent(pantry.address)
  return `https://www.google.com/maps/dir/?api=1&destination=${destination}`
}

// Filter chip component
function FilterChip({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'px-3 py-1.5 rounded-full text-sm font-medium transition-all',
        active
          ? 'bg-emerald-600 text-white'
          : 'bg-white text-zinc-700 hover:bg-zinc-100 border border-zinc-200'
      )}
    >
      {label}
    </button>
  )
}

// Pantry list item
function PantryListItem({ pantry, isSelected, onClick }) {
  const statusColors = {
    OPEN: 'bg-green-100 text-green-700',
    CLOSED: 'bg-red-100 text-red-700',
    WAITLIST: 'bg-amber-100 text-amber-700',
    UNKNOWN: 'bg-zinc-100 text-zinc-600',
  }

  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left p-4 border-b border-zinc-100 hover:bg-zinc-50 transition-colors',
        isSelected && 'bg-emerald-50 border-l-4 border-l-emerald-500'
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-1">
        <h3 className="font-semibold text-zinc-900 text-sm leading-tight">
          {pantry.name}
        </h3>
        <span
          className={clsx(
            'flex-shrink-0 text-xs px-2 py-0.5 rounded-full font-medium',
            statusColors[pantry.status] || statusColors.UNKNOWN
          )}
        >
          {pantry.status}
        </span>
      </div>

      <a
        href={directionsUrl(pantry)}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        className="text-xs text-blue-600 hover:text-blue-800 hover:underline mb-2 line-clamp-1 block"
      >
        {pantry.address}
      </a>

      <div className="flex items-center gap-3 text-xs text-zinc-600">
        {pantry.hours_today && (
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {pantry.hours_today}
          </span>
        )}
        {pantry.is_id_required === false && (
          <span className="flex items-center gap-1 text-emerald-600">
            <Shield className="w-3 h-3" />
            No ID
          </span>
        )}
      </div>
    </button>
  )
}

const statusConfig = {
  OPEN: { label: 'Open', colors: 'bg-green-100 text-green-700 border-green-200' },
  CLOSED: { label: 'Closed', colors: 'bg-red-100 text-red-700 border-red-200' },
  WAITLIST: { label: 'Waitlist', colors: 'bg-amber-100 text-amber-700 border-amber-200' },
  UNKNOWN: { label: 'Unknown', colors: 'bg-zinc-100 text-zinc-600 border-zinc-200' },
}

// Pantry detail panel
function PantryDetailPanel({ pantry, onClose }) {
  if (!pantry) return null

  const status = statusConfig[pantry.status] || statusConfig.UNKNOWN

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      className="absolute right-4 top-20 bottom-4 w-80 bg-white rounded-xl shadow-lg border border-zinc-200 overflow-hidden z-20 flex flex-col"
    >
      {/* Header */}
      <div className="p-4 border-b border-zinc-100">
        <div className="flex items-start justify-between gap-2">
          <h2 className="font-bold text-zinc-900">{pantry.name}</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-zinc-100 rounded-lg transition-colors flex-shrink-0"
          >
            <X className="w-4 h-4 text-zinc-500" />
          </button>
        </div>
        <span
          className={clsx(
            'inline-block mt-2 text-xs px-2 py-1 rounded-full font-medium border',
            status.colors
          )}
        >
          {status.label}
        </span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">

        {/* --- Location & Directions --- */}
        <section>
          <p className="text-[10px] text-zinc-400 uppercase font-semibold tracking-wider mb-2">Location</p>
          <a
            href={directionsUrl(pantry)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-start gap-2 group"
          >
            <MapPin className="w-4 h-4 text-zinc-400 mt-0.5 flex-shrink-0 group-hover:text-emerald-600" />
            <p className="text-sm text-zinc-700 group-hover:text-emerald-700 group-hover:underline">
              {pantry.address}
            </p>
          </a>
          <a
            href={directionsUrl(pantry)}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 text-emerald-700 rounded-lg text-xs font-medium hover:bg-emerald-100 transition-colors"
          >
            <Navigation className="w-3.5 h-3.5" />
            Get Directions
          </a>
        </section>

        {/* --- Hours --- */}
        <section>
          <p className="text-[10px] text-zinc-400 uppercase font-semibold tracking-wider mb-2">Hours</p>
          {pantry.hours_today && (
            <div className="p-3 bg-zinc-50 rounded-lg mb-2">
              <div className="flex items-center gap-1.5 mb-0.5">
                <Clock className="w-3.5 h-3.5 text-zinc-400" />
                <span className="text-[10px] text-zinc-400 uppercase font-medium">Today</span>
              </div>
              <p className="text-sm font-semibold text-zinc-900 ml-5">{pantry.hours_today}</p>
            </div>
          )}
          {pantry.hours_notes && (
            <p className="text-sm text-zinc-600 leading-relaxed">{pantry.hours_notes}</p>
          )}
          {!pantry.hours_today && !pantry.hours_notes && (
            <p className="text-sm text-zinc-400 italic">No hours listed</p>
          )}
        </section>

        {/* --- Access & Requirements --- */}
        <section>
          <p className="text-[10px] text-zinc-400 uppercase font-semibold tracking-wider mb-2">Access & Requirements</p>

          {/* ID Requirement */}
          <div
            className={clsx(
              'p-3 rounded-lg flex items-center gap-2 mb-2',
              pantry.is_id_required ? 'bg-amber-50' : 'bg-green-50'
            )}
          >
            <Shield
              className={clsx(
                'w-4 h-4',
                pantry.is_id_required ? 'text-amber-600' : 'text-green-600'
              )}
            />
            <span
              className={clsx(
                'text-sm font-medium',
                pantry.is_id_required ? 'text-amber-700' : 'text-green-700'
              )}
            >
              {pantry.is_id_required ? 'ID Required' : 'No ID Required'}
            </span>
          </div>

          {/* Residency requirement */}
          {pantry.residency_req && (
            <div className="flex items-start gap-2 text-sm text-zinc-600 mb-2">
              <MapPin className="w-3.5 h-3.5 text-zinc-400 mt-0.5 flex-shrink-0" />
              <span>{pantry.residency_req}</span>
            </div>
          )}

          {/* Eligibility rules */}
          {pantry.eligibility_rules?.length > 0 && (
            <ul className="space-y-1.5 mt-2">
              {pantry.eligibility_rules.map((rule, i) => (
                <li key={i} className="text-sm text-zinc-700 flex items-start gap-2">
                  <span className="text-emerald-500 mt-0.5">•</span>
                  {rule}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* --- Alerts --- */}
        {pantry.special_notes && (
          <section>
            <p className="text-[10px] text-zinc-400 uppercase font-semibold tracking-wider mb-2">Alerts</p>
            <div className="p-3 bg-amber-50 rounded-lg border border-amber-100 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-amber-800">{pantry.special_notes}</p>
            </div>
          </section>
        )}

        {/* --- Data Quality --- */}
        {pantry.confidence != null && (
          <section>
            <p className="text-[10px] text-zinc-400 uppercase font-semibold tracking-wider mb-2">Data Confidence</p>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full"
                  style={{ width: `${pantry.confidence * 10}%` }}
                />
              </div>
              <span className="text-xs text-zinc-500 font-medium">{pantry.confidence}/10</span>
            </div>
          </section>
        )}

        {/* --- Links --- */}
        <section>
          <p className="text-[10px] text-zinc-400 uppercase font-semibold tracking-wider mb-2">Links</p>
          <div className="flex flex-col gap-2">
            <a
              href={directionsUrl(pantry)}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-emerald-600 hover:text-emerald-700"
            >
              <Navigation className="w-4 h-4" />
              Google Maps Directions
            </a>
            {pantry.source_url && (
              <a
                href={pantry.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-emerald-600 hover:text-emerald-700"
              >
                <ExternalLink className="w-4 h-4" />
                Visit Website
              </a>
            )}
          </div>
        </section>
      </div>
    </motion.div>
  )
}

/**
 * Full map experience — self-contained with all hooks and state.
 *
 * Props:
 * - onClose: callback to close/minimize the map experience
 * - initialPantries: optional pre-fetched pantries from the preview section.
 *   When provided, the initial "all pantries" fetch is skipped to avoid a
 *   re-fetch and loading flash. City/radius filtering still works independently.
 */
export default function MapExperience({ onClose, initialPantries }) {
  const [selectedCity, setSelectedCity] = useState(null)
  const [showCitySelector, setShowCitySelector] = useState(true)
  const [radiusMiles, setRadiusMiles] = useState(null)

  const { cities, loading: citiesLoading } = useCities()

  const {
    discover,
    cancel: cancelDiscovery,
    isDiscovering,
    discoveredPantries,
    progress: discoveryProgress,
    error: discoveryError,
  } = useDiscovery()

  const [discoveryDone, setDiscoveryDone] = useState(false)

  const mapCenter = useMemo(() => {
    if (selectedCity) {
      const cityData = cities.find(
        (c) => c.city === selectedCity.city && c.state === selectedCity.state
      )
      if (cityData?.center) return cityData.center
    }
    return null
  }, [selectedCity, cities])

  const [searchQuery, setSearchQuery] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedPantry, setSelectedPantry] = useState(null)
  const [userLocation, setUserLocation] = useState(null)
  const [locating, setLocating] = useState(false)

  const [filters, setFilters] = useState({
    openOnly: false,
    noIdOnly: false,
  })

  const effectiveCenter = useMemo(() => {
    if (userLocation) return userLocation
    if (mapCenter) return mapCenter
    return null
  }, [userLocation, mapCenter])

  const radiusActive = radiusMiles != null && effectiveCenter != null

  // When initialPantries are provided and no city is selected, skip the fetch
  // to avoid a re-fetch/loading flash when transitioning from preview to overlay
  const hasInitialData = initialPantries?.length > 0
  const skipCityFetch = hasInitialData && !selectedCity && !radiusActive

  const {
    pantries: cityPantries,
    loading: cityLoading,
    error: cityError,
    refresh: cityRefresh,
  } = usePantries(
    selectedCity
      ? { city: selectedCity.city, state: selectedCity.state, enabled: !radiusActive }
      : { enabled: !radiusActive && !skipCityFetch }
  )

  const {
    pantries: nearbyPantries,
    loading: nearbyLoading,
    error: nearbyError,
    refresh: nearbyRefresh,
  } = useNearbyPantries({
    lat: effectiveCenter?.lat,
    lng: effectiveCenter?.lng,
    maxDistance: radiusMiles ? milesToMeters(radiusMiles) : null,
    enabled: radiusActive,
  })

  // Use initialPantries when no city/radius is active and we have pre-fetched data
  const basePantries = radiusActive
    ? nearbyPantries
    : skipCityFetch
      ? initialPantries
      : cityPantries

  // Merge discovered pantries (avoid duplicates by _id or pantry_id)
  const pantries = useMemo(() => {
    if (discoveredPantries.length === 0) return basePantries
    const existingIds = new Set(basePantries.map((p) => p._id))
    const newPantries = discoveredPantries.filter(
      (p) => !existingIds.has(p._id) && !existingIds.has(p.pantry_id)
    )
    return [...basePantries, ...newPantries]
  }, [basePantries, discoveredPantries])

  const loading = radiusActive ? nearbyLoading : (skipCityFetch ? false : cityLoading)
  const error = radiusActive ? nearbyError : (skipCityFetch ? null : cityError)
  const refresh = radiusActive ? nearbyRefresh : cityRefresh

  // Track when discovery finishes to show result toast on the overlay
  const prevIsDiscovering = useRef(false)
  useEffect(() => {
    if (prevIsDiscovering.current && !isDiscovering) {
      setDiscoveryDone(true)
    }
    prevIsDiscovering.current = isDiscovering
  }, [isDiscovering])

  // Viewport-based auto-discovery
  const { onMapIdle } = useViewportDiscovery({
    pantries,
    discover,
    isDiscovering,
  })

  // Place search → pan map to selected place
  const [placeCenter, setPlaceCenter] = useState(null)
  const [placeName, setPlaceName] = useState(null)

  const handlePlaceSelect = useCallback(({ lat, lng, name }) => {
    setPlaceCenter({ lat, lng })
    setPlaceName(name)
    setDiscoveryDone(false)
  }, [])

  const handleMapIdle = useCallback((ev) => {
    // @vis.gl/react-google-maps onIdle passes a MapCameraChangedEvent
    // We need the raw google.maps.Map instance for getBounds()
    const map = ev?.map
    if (map) onMapIdle(map)
  }, [onMapIdle])

  // Build a Set of discovered pantry IDs for marker animation
  const discoveredIds = useMemo(() => {
    if (discoveredPantries.length === 0) return null
    const ids = new Set()
    for (const p of discoveredPantries) {
      if (p._id) ids.add(p._id)
      if (p.pantry_id) ids.add(p.pantry_id)
    }
    return ids
  }, [discoveredPantries])

  // Query label for discovery UI
  const discoveryQuery = placeName
    || (selectedCity ? `${selectedCity.city}, ${selectedCity.state}` : null)

  const handleCitySelect = useCallback((city) => {
    setSelectedCity(city)
    setShowCitySelector(false)
    setSelectedPantry(null)
  }, [])

  const filteredPantries = useMemo(() => {
    let result = pantries

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      result = result.filter(
        (p) =>
          p.name?.toLowerCase().includes(query) ||
          p.address?.toLowerCase().includes(query)
      )
    }

    if (filters.openOnly) {
      result = result.filter((p) => p.status === 'OPEN')
    }

    if (filters.noIdOnly) {
      result = result.filter((p) => p.is_id_required === false)
    }

    return result
  }, [pantries, searchQuery, filters])

  const handleLocateUser = useCallback(() => {
    if (!navigator.geolocation) return

    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        })
        setLocating(false)
        if (radiusMiles == null) setRadiusMiles(25)
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }, [radiusMiles])

  const radiusMeters = radiusActive ? milesToMeters(radiusMiles) : null
  const radiusZoom = radiusActive ? radiusToZoom(radiusMiles) : null

  const handlePantrySelect = (pantry) => {
    setSelectedPantry(pantry)
  }

  return (
    <div className="h-full w-full flex bg-zinc-100 overflow-hidden">
      {/* Sidebar */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.aside
            initial={{ x: -320 }}
            animate={{ x: 0 }}
            exit={{ x: -320 }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="w-80 bg-white border-r border-zinc-200 flex flex-col z-30"
          >
            {/* Sidebar header */}
            <div className="p-4 border-b border-zinc-100">
              <div className="flex items-center justify-between mb-4">
                <button
                  onClick={onClose}
                  className="flex items-center gap-2"
                >
                  <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center">
                    <MapPin className="w-4 h-4 text-white" />
                  </div>
                  <span className="font-bold text-zinc-900">EquiTable</span>
                </button>
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="p-1.5 hover:bg-zinc-100 rounded-lg transition-colors"
                >
                  <ChevronLeft className="w-4 h-4 text-zinc-500" />
                </button>
              </div>

              {/* City dropdown */}
              <div className="mb-3">
                <CityDropdown
                  cities={cities}
                  selectedCity={selectedCity}
                  onSelect={handleCitySelect}
                  loading={citiesLoading}
                />
              </div>

              {/* Radius slider */}
              <div className="mb-3">
                <RadiusSlider
                  value={radiusMiles}
                  onChange={setRadiusMiles}
                  centerLabel={
                    userLocation
                      ? 'your location'
                      : selectedCity
                        ? selectedCity.city
                        : null
                  }
                  disabled={!effectiveCenter}
                />
              </div>

              {/* Filter by name/address */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter pantries..."
                  className="w-full pl-10 pr-4 py-2.5 bg-zinc-50 border border-zinc-200 rounded-lg text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 hover:bg-zinc-200 rounded"
                  >
                    <X className="w-3.5 h-3.5 text-zinc-400" />
                  </button>
                )}
              </div>
            </div>

            {/* Filters */}
            <div className="p-4 border-b border-zinc-100 flex gap-2">
              <FilterChip
                label="Open Now"
                active={filters.openOnly}
                onClick={() => setFilters((f) => ({ ...f, openOnly: !f.openOnly }))}
              />
              <FilterChip
                label="No ID"
                active={filters.noIdOnly}
                onClick={() => setFilters((f) => ({ ...f, noIdOnly: !f.noIdOnly }))}
              />
            </div>

            {/* Results count */}
            <div className="px-4 py-2 text-xs text-zinc-500 bg-zinc-50 border-b border-zinc-100">
              {radiusActive
                ? `${filteredPantries.length} pantries within ${radiusMiles} mi`
                : `${filteredPantries.length} of ${pantries.length} pantries`}
            </div>

            {/* Pantry list */}
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="w-6 h-6 text-zinc-400 animate-spin" />
                </div>
              ) : error ? (
                <div className="p-4 text-center">
                  <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
                  <p className="text-sm text-red-600">{error}</p>
                  <button
                    onClick={refresh}
                    className="mt-2 text-sm text-emerald-600 hover:underline"
                  >
                    Retry
                  </button>
                </div>
              ) : filteredPantries.length === 0 ? (
                <div className="p-4 text-center text-zinc-500 text-sm">
                  No pantries found
                </div>
              ) : (
                filteredPantries.map((pantry) => (
                  <PantryListItem
                    key={pantry._id}
                    pantry={pantry}
                    isSelected={selectedPantry?._id === pantry._id}
                    onClick={() => handlePantrySelect(pantry)}
                  />
                ))
              )}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Main map area */}
      <div className="flex-1 relative">
        {/* Floating controls */}
        <div className="absolute top-4 left-4 z-20 flex gap-2">
          {!sidebarOpen && (
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-3 bg-white rounded-xl shadow-lg border border-zinc-200 hover:bg-zinc-50 transition-colors"
            >
              <Menu className="w-5 h-5 text-zinc-700" />
            </button>
          )}
        </div>

        {/* Near me button */}
        <button
          onClick={handleLocateUser}
          disabled={locating}
          className="absolute bottom-6 right-6 z-20 flex items-center gap-2 px-4 py-3 bg-white rounded-xl shadow-lg border border-zinc-200 hover:bg-zinc-50 transition-colors disabled:opacity-50"
        >
          <Navigation className={clsx('w-5 h-5 text-emerald-600', locating && 'animate-pulse')} />
          <span className="font-medium text-zinc-700">
            {locating ? 'Locating...' : 'Near Me'}
          </span>
        </button>

        {/* Legend */}
        <div className="absolute bottom-6 left-4 z-20 flex gap-3 px-4 py-3 bg-white/95 backdrop-blur rounded-xl shadow-lg border border-zinc-200">
          <div className="flex items-center gap-1.5 text-xs text-zinc-600">
            <span className="w-3 h-3 rounded-full bg-green-500" />
            Open
          </div>
          <div className="flex items-center gap-1.5 text-xs text-zinc-600">
            <span className="w-3 h-3 rounded-full bg-amber-500" />
            ID Req
          </div>
          <div className="flex items-center gap-1.5 text-xs text-zinc-600">
            <span className="w-3 h-3 rounded-full bg-zinc-400" />
            Unknown
          </div>
          <div className="flex items-center gap-1.5 text-xs text-zinc-600">
            <span className="w-3 h-3 rounded-full bg-red-500" />
            Closed
          </div>
        </div>

        {/* Map */}
        <PantryMapClean
          pantries={filteredPantries}
          userLocation={userLocation}
          selectedPantry={selectedPantry}
          onPantrySelect={handlePantrySelect}
          center={placeCenter || (radiusActive ? effectiveCenter : mapCenter)}
          radiusCenter={radiusActive ? effectiveCenter : null}
          radiusMeters={radiusMeters}
          zoom={radiusZoom}
          className="w-full h-full"
          discoveredIds={discoveredIds}
          onIdle={handleMapIdle}
          onPlaceSelect={handlePlaceSelect}
        />

        {/* Discovery overlay — map-level progress + toast */}
        <DiscoveryOverlay
          isDiscovering={isDiscovering}
          discoveryDone={discoveryDone}
          progress={discoveryProgress}
          error={discoveryError}
          query={discoveryQuery}
          onCancel={cancelDiscovery}
          onDismiss={() => setDiscoveryDone(false)}
          onRetry={() => setDiscoveryDone(false)}
        />

        {/* Detail panel */}
        <AnimatePresence>
          {selectedPantry && (
            <PantryDetailPanel
              pantry={selectedPantry}
              onClose={() => setSelectedPantry(null)}
            />
          )}
        </AnimatePresence>

        {/* City selector overlay */}
        <AnimatePresence>
          {showCitySelector && (
            <CitySelector
              cities={cities}
              loading={citiesLoading}
              onSelect={handleCitySelect}
              onClose={selectedCity ? () => setShowCitySelector(false) : null}
            />
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
