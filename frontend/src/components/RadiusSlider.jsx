import { useState, useEffect, useRef } from 'react'
import { Crosshair } from 'lucide-react'
import { clsx } from 'clsx'

const MIN_MILES = 1
const MAX_MILES = 2000
const LOG_MIN = Math.log(MIN_MILES)
const LOG_MAX = Math.log(MAX_MILES)

// Slider position (0-100) -> miles (logarithmic scale)
function sliderToMiles(value) {
  return Math.round(Math.exp(LOG_MIN + (value / 100) * (LOG_MAX - LOG_MIN)))
}

// Miles -> slider position (0-100)
function milesToSlider(miles) {
  if (miles <= MIN_MILES) return 0
  if (miles >= MAX_MILES) return 100
  return Math.round(((Math.log(miles) - LOG_MIN) / (LOG_MAX - LOG_MIN)) * 100)
}

// Miles -> meters for API
export function milesToMeters(miles) {
  return Math.round(miles * 1609.34)
}

// Radius -> suggested zoom level
export function radiusToZoom(radiusMiles) {
  if (radiusMiles <= 2) return 14
  if (radiusMiles <= 10) return 12
  if (radiusMiles <= 50) return 10
  if (radiusMiles <= 200) return 8
  if (radiusMiles <= 1000) return 6
  return 4
}

function formatMiles(miles) {
  if (miles >= 1000) return `${(miles / 1000).toFixed(1)}k mi`
  return `${miles} mi`
}

const TICK_MILES = [1, 5, 25, 100, 500, 2000]

export default function RadiusSlider({ value, onChange, centerLabel, disabled }) {
  const active = value != null
  const [sliderPos, setSliderPos] = useState(active ? milesToSlider(value) : 50)
  const debounceRef = useRef(null)

  // Sync slider position when value changes externally
  useEffect(() => {
    if (value != null) {
      setSliderPos(milesToSlider(value))
    }
  }, [value])

  const handleToggle = () => {
    if (active) {
      onChange(null)
    } else {
      const miles = sliderToMiles(sliderPos)
      onChange(miles)
    }
  }

  const handleSliderChange = (e) => {
    const pos = Number(e.target.value)
    setSliderPos(pos)
    const miles = sliderToMiles(pos)

    // Debounce the API call
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      onChange(miles)
    }, 300)
  }

  const displayMiles = sliderToMiles(sliderPos)

  return (
    <div className={clsx('rounded-lg border p-3 transition-colors', active ? 'bg-emerald-50/50 border-emerald-200' : 'bg-zinc-50 border-zinc-200')}>
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-zinc-600">
          <Crosshair className="w-3.5 h-3.5" />
          Radius
        </span>
        <button
          onClick={handleToggle}
          disabled={disabled}
          className={clsx(
            'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
            active ? 'bg-emerald-500' : 'bg-zinc-300',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          <span
            className={clsx(
              'inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform shadow-sm',
              active ? 'translate-x-4.5' : 'translate-x-0.5'
            )}
          />
        </button>
      </div>

      {active && (
        <>
          {/* Current value */}
          <div className="text-center mb-2">
            <span className="text-lg font-bold text-emerald-700">{formatMiles(displayMiles)}</span>
            {centerLabel && (
              <span className="text-xs text-zinc-500 ml-1">from {centerLabel}</span>
            )}
          </div>

          {/* Slider */}
          <input
            type="range"
            min={0}
            max={100}
            value={sliderPos}
            onChange={handleSliderChange}
            className="w-full h-1.5 bg-zinc-200 rounded-full appearance-none cursor-pointer accent-emerald-500 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-emerald-500 [&::-webkit-slider-thumb]:shadow-md"
          />

          {/* Tick labels */}
          <div className="flex justify-between mt-1 px-0.5">
            {TICK_MILES.map((m) => (
              <span key={m} className="text-[10px] text-zinc-400">
                {m >= 1000 ? `${m / 1000}k` : m}
              </span>
            ))}
          </div>
        </>
      )}

      {!active && !disabled && (
        <p className="text-[11px] text-zinc-400 mt-0.5">
          Enable to filter by distance
        </p>
      )}

      {disabled && (
        <p className="text-[11px] text-zinc-400 mt-0.5">
          Select a city or use Near Me first
        </p>
      )}
    </div>
  )
}
