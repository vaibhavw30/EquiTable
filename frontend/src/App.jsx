import { useState } from 'react'
import { RefreshCw, Loader2, AlertTriangle } from 'lucide-react'
import usePantries from './hooks/usePantries'
import PantryMap from './components/PantryMap'

function App() {
  const { pantries, loading, error, refresh } = usePantries()
  const [showNoIdOnly, setShowNoIdOnly] = useState(false)

  const filteredPantries = showNoIdOnly
    ? pantries.filter((p) => p.is_id_required === false)
    : pantries

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      {/* Sidebar overlay */}
      <div className="absolute top-4 left-4 z-10 bg-white/95 backdrop-blur rounded-xl shadow-lg p-5 w-72 space-y-4">
        <div>
          <h1 className="text-xl font-bold text-emerald-700">EquiTable</h1>
          <p className="text-xs text-gray-500">AI-Powered Food Rescue Agent</p>
        </div>

        {/* Status bar */}
        <div className="text-xs text-gray-500">
          {loading ? (
            <span className="flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" /> Loading...
            </span>
          ) : error ? (
            <span className="flex items-center gap-1 text-red-600">
              <AlertTriangle className="w-3 h-3" /> {error}
            </span>
          ) : (
            <span>
              {filteredPantries.length} of {pantries.length} pantries shown
            </span>
          )}
        </div>

        {/* No ID toggle */}
        <label className="flex items-center justify-between cursor-pointer">
          <span className="text-sm font-medium text-gray-700">
            No ID Required
          </span>
          <button
            role="switch"
            aria-checked={showNoIdOnly}
            onClick={() => setShowNoIdOnly((v) => !v)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              showNoIdOnly ? 'bg-emerald-500' : 'bg-gray-300'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                showNoIdOnly ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </label>

        {/* Refresh button */}
        <button
          onClick={refresh}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-lg transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>

        {/* Legend */}
        <div className="border-t pt-3 space-y-1.5">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Legend</p>
          <div className="flex items-center gap-2 text-xs text-gray-600">
            <span className="w-3 h-3 rounded-full bg-green-500 inline-block" />
            Open &middot; No ID
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-600">
            <span className="w-3 h-3 rounded-full bg-amber-500 inline-block" />
            Open &middot; ID Required
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-600">
            <span className="w-3 h-3 rounded-full bg-red-500 inline-block" />
            Closed
          </div>
        </div>
      </div>

      {/* Full-screen map */}
      <PantryMap pantries={filteredPantries} />
    </div>
  )
}

export default App
