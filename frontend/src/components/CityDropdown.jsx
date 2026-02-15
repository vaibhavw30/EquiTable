import { useState, useRef, useEffect } from 'react'
import { ChevronDown, MapPin, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'

export default function CityDropdown({ cities, selectedCity, onSelect, loading }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  // Close on outside click
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const label = selectedCity
    ? `${selectedCity.city}, ${selectedCity.state}`
    : 'All Cities'

  return (
    <div ref={ref} className="relative w-full">
      <button
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          'w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all border',
          selectedCity
            ? 'bg-emerald-50 border-emerald-200 text-emerald-800 hover:bg-emerald-100'
            : 'bg-zinc-50 border-zinc-200 text-zinc-700 hover:bg-zinc-100'
        )}
      >
        <span className="flex items-center gap-2 truncate">
          <MapPin className="w-4 h-4 flex-shrink-0" />
          {label}
        </span>
        <ChevronDown
          className={clsx(
            'w-4 h-4 flex-shrink-0 transition-transform',
            open && 'rotate-180'
          )}
        />
      </button>

      {open && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-zinc-200 rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="w-4 h-4 text-zinc-400 animate-spin" />
            </div>
          ) : (
            <>
              {/* All Cities option */}
              <button
                onClick={() => { onSelect(null); setOpen(false) }}
                className={clsx(
                  'w-full text-left px-3 py-2.5 text-sm hover:bg-zinc-50 transition-colors border-b border-zinc-100',
                  !selectedCity && 'bg-emerald-50 text-emerald-700 font-medium'
                )}
              >
                All Cities
              </button>

              {cities.map((city) => {
                const isActive =
                  selectedCity?.city === city.city &&
                  selectedCity?.state === city.state

                return (
                  <button
                    key={`${city.city}-${city.state}`}
                    onClick={() => { onSelect(city); setOpen(false) }}
                    className={clsx(
                      'w-full text-left px-3 py-2.5 text-sm hover:bg-zinc-50 transition-colors',
                      isActive && 'bg-emerald-50 text-emerald-700 font-medium'
                    )}
                  >
                    <span className="flex items-center justify-between">
                      <span>
                        {city.city}, {city.state}
                      </span>
                      <span className="text-xs text-zinc-400">
                        {city.count}
                      </span>
                    </span>
                  </button>
                )
              })}
            </>
          )}
        </div>
      )}
    </div>
  )
}
