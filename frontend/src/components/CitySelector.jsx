import { motion } from 'framer-motion'
import { MapPin, X, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'

export default function CitySelector({ cities, loading, onSelect, onClose }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="absolute inset-0 z-40 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="bg-white rounded-2xl shadow-2xl border border-zinc-200 max-w-lg w-full mx-4 overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-zinc-100">
          <div>
            <h2 className="text-lg font-bold text-zinc-900">Choose a City</h2>
            <p className="text-sm text-zinc-500 mt-0.5">
              Select a city to explore food pantries
            </p>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 hover:bg-zinc-100 rounded-lg transition-colors"
            >
              <X className="w-4 h-4 text-zinc-500" />
            </button>
          )}
        </div>

        {/* City grid */}
        <div className="p-5">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 text-zinc-400 animate-spin" />
            </div>
          ) : cities.length === 0 ? (
            <p className="text-center text-zinc-500 py-8">No cities available</p>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {cities.map((city) => (
                <button
                  key={`${city.city}-${city.state}`}
                  onClick={() => onSelect(city)}
                  className={clsx(
                    'flex items-start gap-3 p-4 rounded-xl border border-zinc-200',
                    'hover:border-emerald-300 hover:bg-emerald-50 transition-all text-left',
                    'group'
                  )}
                >
                  <MapPin className="w-5 h-5 text-emerald-500 mt-0.5 flex-shrink-0 group-hover:scale-110 transition-transform" />
                  <div>
                    <p className="font-semibold text-zinc-900 text-sm">
                      {city.city}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {city.state} &middot; {city.count} {city.count === 1 ? 'pantry' : 'pantries'}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}
