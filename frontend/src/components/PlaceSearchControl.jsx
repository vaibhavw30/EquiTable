import { useRef, useEffect, useState } from 'react'
import { MapControl, ControlPosition, useMapsLibrary } from '@vis.gl/react-google-maps'
import { Search } from 'lucide-react'

/**
 * Google Places Autocomplete search bar rendered on the map.
 * Uses MapControl to position it at the top of the map.
 *
 * Props:
 * - onPlaceSelect({ lat, lng, name }): called when user selects a place
 */
export default function PlaceSearchControl({ onPlaceSelect }) {
  const inputRef = useRef(null)
  const autocompleteRef = useRef(null)
  const placesLib = useMapsLibrary('places')
  const [inputValue, setInputValue] = useState('')

  useEffect(() => {
    if (!placesLib || !inputRef.current || autocompleteRef.current) return

    const autocomplete = new placesLib.Autocomplete(inputRef.current, {
      fields: ['geometry', 'name', 'formatted_address'],
    })

    autocomplete.addListener('place_changed', () => {
      const place = autocomplete.getPlace()
      if (!place?.geometry?.location) return

      const lat = place.geometry.location.lat()
      const lng = place.geometry.location.lng()
      const name = place.name || place.formatted_address || ''

      setInputValue(name)
      onPlaceSelect?.({ lat, lng, name })
    })

    autocompleteRef.current = autocomplete
  }, [placesLib, onPlaceSelect])

  return (
    <MapControl position={ControlPosition.TOP}>
      <div className="mt-2.5 mx-auto" style={{ width: 'min(400px, calc(100vw - 120px))' }}>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400 pointer-events-none" />
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Search for a location..."
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-zinc-200 rounded-xl text-sm text-zinc-900 placeholder:text-zinc-400 shadow-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
            data-testid="place-search-input"
          />
        </div>
      </div>
    </MapControl>
  )
}
