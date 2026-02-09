import { useState, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Search,
  X,
  Navigation,
  Filter,
  ChevronLeft,
  ChevronRight,
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
import PantryMapClean from '../components/PantryMapClean'

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

      <p className="text-xs text-zinc-500 mb-2 line-clamp-1">{pantry.address}</p>

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

// Pantry detail panel
function PantryDetailPanel({ pantry, onClose }) {
  if (!pantry) return null

  const statusColors = {
    OPEN: 'bg-green-100 text-green-700 border-green-200',
    CLOSED: 'bg-red-100 text-red-700 border-red-200',
    WAITLIST: 'bg-amber-100 text-amber-700 border-amber-200',
    UNKNOWN: 'bg-zinc-100 text-zinc-600 border-zinc-200',
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      className="absolute right-4 top-20 bottom-4 w-80 bg-white rounded-xl shadow-lg border border-zinc-200 overflow-hidden z-20"
    >
      {/* Header */}
      <div className="p-4 border-b border-zinc-100">
        <div className="flex items-start justify-between gap-2">
          <h2 className="font-bold text-zinc-900">{pantry.name}</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-zinc-100 rounded-lg transition-colors"
          >
            <X className="w-4 h-4 text-zinc-500" />
          </button>
        </div>
        <span
          className={clsx(
            'inline-block mt-2 text-xs px-2 py-1 rounded-full font-medium border',
            statusColors[pantry.status] || statusColors.UNKNOWN
          )}
        >
          {pantry.status}
        </span>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4 overflow-y-auto max-h-[calc(100%-80px)]">
        {/* Address */}
        <div className="flex items-start gap-2">
          <MapPin className="w-4 h-4 text-zinc-400 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-zinc-700">{pantry.address}</p>
        </div>

        {/* Hours */}
        {pantry.hours_today && (
          <div className="p-3 bg-zinc-50 rounded-lg">
            <p className="text-xs text-zinc-500 uppercase font-medium mb-1">Today</p>
            <p className="text-sm font-semibold text-zinc-900">{pantry.hours_today}</p>
          </div>
        )}

        {pantry.hours_notes && (
          <div>
            <p className="text-xs text-zinc-500 uppercase font-medium mb-1">Hours</p>
            <p className="text-sm text-zinc-700">{pantry.hours_notes}</p>
          </div>
        )}

        {/* ID Requirement */}
        <div
          className={clsx(
            'p-3 rounded-lg flex items-center gap-2',
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

        {/* Eligibility */}
        {pantry.eligibility_rules?.length > 0 && (
          <div>
            <p className="text-xs text-zinc-500 uppercase font-medium mb-2">Requirements</p>
            <ul className="space-y-1.5">
              {pantry.eligibility_rules.map((rule, i) => (
                <li key={i} className="text-sm text-zinc-700 flex items-start gap-2">
                  <span className="text-emerald-500 mt-1">•</span>
                  {rule}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Special notes */}
        {pantry.special_notes && (
          <div className="p-3 bg-amber-50 rounded-lg border border-amber-100">
            <p className="text-sm text-amber-800">{pantry.special_notes}</p>
          </div>
        )}

        {/* Confidence */}
        {pantry.confidence != null && (
          <div>
            <p className="text-xs text-zinc-500 uppercase font-medium mb-1">Data Confidence</p>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full"
                  style={{ width: `${pantry.confidence * 10}%` }}
                />
              </div>
              <span className="text-xs text-zinc-500">{pantry.confidence}/10</span>
            </div>
          </div>
        )}

        {/* Source link */}
        {pantry.source_url && (
          <a
            href={pantry.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm text-emerald-600 hover:text-emerald-700"
          >
            <ExternalLink className="w-4 h-4" />
            View website
          </a>
        )}
      </div>
    </motion.div>
  )
}

// Main Map Page
export default function MapPage() {
  const { pantries, loading, error, refresh } = usePantries()
  const [searchQuery, setSearchQuery] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedPantry, setSelectedPantry] = useState(null)
  const [userLocation, setUserLocation] = useState(null)
  const [locating, setLocating] = useState(false)

  // Filters
  const [filters, setFilters] = useState({
    openOnly: false,
    noIdOnly: false,
  })

  // Smart filtering
  const filteredPantries = useMemo(() => {
    let result = pantries

    // Text search
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      result = result.filter(
        (p) =>
          p.name?.toLowerCase().includes(query) ||
          p.address?.toLowerCase().includes(query)
      )
    }

    // Status filter
    if (filters.openOnly) {
      result = result.filter((p) => p.status === 'OPEN')
    }

    // ID filter
    if (filters.noIdOnly) {
      result = result.filter((p) => p.is_id_required === false)
    }

    return result
  }, [pantries, searchQuery, filters])

  // Geolocation
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
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }, [])

  const handlePantrySelect = (pantry) => {
    setSelectedPantry(pantry)
  }

  return (
    <div className="h-screen w-screen flex bg-zinc-100 overflow-hidden">
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
                <Link to="/" className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center">
                    <MapPin className="w-4 h-4 text-white" />
                  </div>
                  <span className="font-bold text-zinc-900">EquiTable</span>
                </Link>
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="p-1.5 hover:bg-zinc-100 rounded-lg transition-colors"
                >
                  <ChevronLeft className="w-4 h-4 text-zinc-500" />
                </button>
              </div>

              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search pantries..."
                  className="w-full pl-10 pr-4 py-2.5 bg-zinc-50 border border-zinc-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
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
              {filteredPantries.length} of {pantries.length} pantries
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
          {/* Sidebar toggle (when closed) */}
          {!sidebarOpen && (
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-3 bg-white rounded-xl shadow-lg border border-zinc-200 hover:bg-zinc-50 transition-colors"
            >
              <Menu className="w-5 h-5 text-zinc-700" />
            </button>
          )}

          {/* Home button */}
          <Link
            to="/"
            className="p-3 bg-white rounded-xl shadow-lg border border-zinc-200 hover:bg-zinc-50 transition-colors"
          >
            <Home className="w-5 h-5 text-zinc-700" />
          </Link>
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
          className="w-full h-full"
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
      </div>
    </div>
  )
}
