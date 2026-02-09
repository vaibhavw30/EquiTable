import { useState, useCallback } from 'react'
import {
  APIProvider,
  Map,
  AdvancedMarker,
  InfoWindow,
  Pin,
} from '@vis.gl/react-google-maps'
import { Clock, Shield, Users } from 'lucide-react'

const MAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY

// Atlanta default center
const DEFAULT_CENTER = { lat: 33.78, lng: -84.40 }
const DEFAULT_ZOOM = 12

function markerColors(pantry) {
  if (pantry.status === 'CLOSED') {
    return { background: '#EF4444', glyphColor: '#fff', borderColor: '#B91C1C' }
  }
  if (pantry.is_id_required) {
    return { background: '#F59E0B', glyphColor: '#fff', borderColor: '#D97706' }
  }
  return { background: '#22C55E', glyphColor: '#fff', borderColor: '#16A34A' }
}

export default function PantryMap({ pantries }) {
  const [selectedPantry, setSelectedPantry] = useState(null)

  const handleMarkerClick = useCallback((pantry) => {
    setSelectedPantry(pantry)
  }, [])

  return (
    <APIProvider apiKey={MAPS_KEY}>
      <Map
        defaultCenter={DEFAULT_CENTER}
        defaultZoom={DEFAULT_ZOOM}
        mapId="equitable-map"
        gestureHandling="greedy"
        disableDefaultUI={false}
        className="w-full h-full"
      >
        {pantries.map((pantry) => {
          const colors = markerColors(pantry)
          return (
            <AdvancedMarker
              key={pantry._id}
              position={{ lat: pantry.lat, lng: pantry.lng }}
              onClick={() => handleMarkerClick(pantry)}
            >
              <Pin
                background={colors.background}
                glyphColor={colors.glyphColor}
                borderColor={colors.borderColor}
              />
            </AdvancedMarker>
          )
        })}

        {selectedPantry && (
          <InfoWindow
            position={{ lat: selectedPantry.lat, lng: selectedPantry.lng }}
            onCloseClick={() => setSelectedPantry(null)}
            pixelOffset={[0, -40]}
          >
            <div className="max-w-xs p-1">
              <h3 className="font-bold text-gray-900 text-sm mb-1">
                {selectedPantry.name}
              </h3>

              {selectedPantry.hours_today && (
                <div className="flex items-center gap-1 text-xs text-gray-600 mb-1">
                  <Clock className="w-3 h-3" />
                  <span>Today: {selectedPantry.hours_today}</span>
                </div>
              )}

              {selectedPantry.is_id_required != null && (
                <div className="flex items-center gap-1 text-xs text-gray-600 mb-1">
                  <Shield className="w-3 h-3" />
                  <span>
                    {selectedPantry.is_id_required
                      ? 'ID Required'
                      : 'No ID Required'}
                  </span>
                </div>
              )}

              {selectedPantry.eligibility_rules?.length > 0 && (
                <div className="flex items-start gap-1 text-xs text-gray-600">
                  <Users className="w-3 h-3 mt-0.5" />
                  <ul className="space-y-0.5">
                    {selectedPantry.eligibility_rules.map((rule, i) => (
                      <li key={i}>{rule}</li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedPantry.special_notes && (
                <div className="mt-1 text-xs text-amber-700 bg-amber-50 rounded p-1">
                  {selectedPantry.special_notes}
                </div>
              )}
            </div>
          </InfoWindow>
        )}
      </Map>
    </APIProvider>
  )
}
