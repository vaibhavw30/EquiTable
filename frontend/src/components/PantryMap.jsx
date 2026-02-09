import { useState, useCallback, useEffect } from 'react'
import {
  APIProvider,
  Map,
  AdvancedMarker,
  InfoWindow,
  Pin,
  useMap,
} from '@vis.gl/react-google-maps'
import { Clock, Shield, Users, MapPin, ExternalLink } from 'lucide-react'
import { clsx } from 'clsx'

const MAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY

// Atlanta default center
const DEFAULT_CENTER = { lat: 33.78, lng: -84.40 }
const DEFAULT_ZOOM = 12

// Dark mode map style - Cyberpunk aesthetic
const DARK_MAP_STYLE = [
  { elementType: 'geometry', stylers: [{ color: '#0a0a0a' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#0a0a0a' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#525252' }] },
  {
    featureType: 'administrative',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#27272a' }],
  },
  {
    featureType: 'administrative.land_parcel',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#3f3f46' }],
  },
  {
    featureType: 'poi',
    elementType: 'geometry',
    stylers: [{ color: '#18181b' }],
  },
  {
    featureType: 'poi',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#52525b' }],
  },
  {
    featureType: 'poi.park',
    elementType: 'geometry',
    stylers: [{ color: '#0f1f0f' }],
  },
  {
    featureType: 'poi.park',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#3d5a3d' }],
  },
  {
    featureType: 'road',
    elementType: 'geometry',
    stylers: [{ color: '#1c1c1e' }],
  },
  {
    featureType: 'road',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#27272a' }],
  },
  {
    featureType: 'road',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#71717a' }],
  },
  {
    featureType: 'road.highway',
    elementType: 'geometry',
    stylers: [{ color: '#1e3a1e' }],
  },
  {
    featureType: 'road.highway',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#0f290f' }],
  },
  {
    featureType: 'road.highway',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#4ade80' }],
  },
  {
    featureType: 'transit',
    elementType: 'geometry',
    stylers: [{ color: '#18181b' }],
  },
  {
    featureType: 'transit.station',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#52525b' }],
  },
  {
    featureType: 'water',
    elementType: 'geometry',
    stylers: [{ color: '#0c1929' }],
  },
  {
    featureType: 'water',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#1e3a5f' }],
  },
  // Hide highway shields for cleaner look
  {
    featureType: 'road.highway',
    elementType: 'labels.icon',
    stylers: [{ visibility: 'off' }],
  },
]

/**
 * 4-color pin logic:
 * - CLOSED → Red
 * - UNKNOWN or WAITLIST → Gray (neutral/uncertain)
 * - OPEN + ID required → Yellow (restricted)
 * - OPEN + no ID → Green (fully accessible)
 */
function markerColors(pantry) {
  // Red: Closed
  if (pantry.status === 'CLOSED') {
    return { background: '#EF4444', glyphColor: '#fff', borderColor: '#B91C1C' }
  }
  // Gray: Unknown or Waitlist (uncertain availability)
  if (pantry.status === 'UNKNOWN' || pantry.status === 'WAITLIST') {
    return { background: '#52525b', glyphColor: '#fff', borderColor: '#3f3f46' }
  }
  // Yellow: Open but ID required
  if (pantry.is_id_required) {
    return { background: '#F59E0B', glyphColor: '#fff', borderColor: '#D97706' }
  }
  // Emerald Green: Open and no ID required (fully accessible)
  return { background: '#10B981', glyphColor: '#fff', borderColor: '#059669' }
}

// Status badge styling
function getStatusStyle(status) {
  switch (status) {
    case 'OPEN':
      return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
    case 'CLOSED':
      return 'bg-red-500/20 text-red-400 border-red-500/30'
    case 'WAITLIST':
      return 'bg-amber-500/20 text-amber-400 border-amber-500/30'
    default:
      return 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30'
  }
}

// Inner component to access map instance
function MapContent({ pantries, userLocation }) {
  const map = useMap()
  const [selectedPantry, setSelectedPantry] = useState(null)

  const handleMarkerClick = useCallback((pantry) => {
    setSelectedPantry(pantry)
  }, [])

  // Pan to user location when it changes
  useEffect(() => {
    if (userLocation && map) {
      map.panTo(userLocation)
      map.setZoom(14)
    }
  }, [userLocation, map])

  return (
    <>
      {/* Pantry markers */}
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

      {/* User location marker (pulsing emerald dot) */}
      {userLocation && (
        <AdvancedMarker position={userLocation}>
          <div className="relative">
            <div className="w-4 h-4 bg-emerald-400 rounded-full border-2 border-zinc-900 shadow-[0_0_10px_rgba(52,211,153,0.8)]" />
            <div className="absolute inset-0 w-4 h-4 bg-emerald-400 rounded-full animate-ping opacity-50" />
          </div>
        </AdvancedMarker>
      )}

      {/* InfoWindow for selected pantry - Dark themed */}
      {selectedPantry && (
        <InfoWindow
          position={{ lat: selectedPantry.lat, lng: selectedPantry.lng }}
          onCloseClick={() => setSelectedPantry(null)}
          pixelOffset={[0, -40]}
        >
          <div className="max-w-xs p-2 font-sans">
            {/* Header with status */}
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="font-bold text-zinc-900 text-sm leading-tight">
                {selectedPantry.name}
              </h3>
              <span
                className={clsx(
                  'flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded border font-semibold uppercase tracking-wide',
                  getStatusStyle(selectedPantry.status)
                )}
              >
                {selectedPantry.status}
              </span>
            </div>

            {/* Address */}
            <div className="flex items-start gap-1.5 text-xs text-zinc-600 mb-2">
              <MapPin className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{selectedPantry.address}</span>
            </div>

            {/* Hours today */}
            {selectedPantry.hours_today && (
              <div className="flex items-center gap-1.5 text-xs text-zinc-700 mb-1.5 bg-zinc-100 rounded px-2 py-1">
                <Clock className="w-3 h-3 text-emerald-600" />
                <span>
                  <strong>Today:</strong> {selectedPantry.hours_today}
                </span>
              </div>
            )}

            {/* ID Requirement */}
            {selectedPantry.is_id_required != null && (
              <div
                className={clsx(
                  'flex items-center gap-1.5 text-xs mb-1.5 rounded px-2 py-1',
                  selectedPantry.is_id_required
                    ? 'bg-amber-50 text-amber-700'
                    : 'bg-emerald-50 text-emerald-700'
                )}
              >
                <Shield className="w-3 h-3" />
                <span>
                  {selectedPantry.is_id_required
                    ? 'ID Required'
                    : 'No ID Required'}
                </span>
              </div>
            )}

            {/* Eligibility rules */}
            {selectedPantry.eligibility_rules?.length > 0 && (
              <div className="mt-2 pt-2 border-t border-zinc-200">
                <div className="flex items-start gap-1.5 text-xs text-zinc-600">
                  <Users className="w-3 h-3 mt-0.5 flex-shrink-0" />
                  <ul className="space-y-0.5">
                    {selectedPantry.eligibility_rules.slice(0, 2).map((rule, i) => (
                      <li key={i} className="leading-tight">
                        {rule}
                      </li>
                    ))}
                    {selectedPantry.eligibility_rules.length > 2 && (
                      <li className="text-zinc-400 italic">
                        +{selectedPantry.eligibility_rules.length - 2} more...
                      </li>
                    )}
                  </ul>
                </div>
              </div>
            )}

            {/* Special notes */}
            {selectedPantry.special_notes && (
              <div className="mt-2 text-xs text-amber-700 bg-amber-50 rounded px-2 py-1.5 border border-amber-200/50">
                {selectedPantry.special_notes}
              </div>
            )}

            {/* Confidence indicator */}
            {selectedPantry.confidence != null && (
              <div className="mt-2 pt-2 border-t border-zinc-200 flex items-center justify-between">
                <span className="text-[10px] text-zinc-400 uppercase tracking-wide">
                  Data confidence
                </span>
                <div className="flex gap-0.5">
                  {[...Array(10)].map((_, i) => (
                    <div
                      key={i}
                      className={clsx(
                        'w-1.5 h-3 rounded-sm',
                        i < selectedPantry.confidence
                          ? 'bg-emerald-500'
                          : 'bg-zinc-200'
                      )}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Source link */}
            {selectedPantry.source_url && (
              <a
                href={selectedPantry.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 flex items-center gap-1 text-[10px] text-emerald-600 hover:text-emerald-700"
              >
                <ExternalLink className="w-3 h-3" />
                View source
              </a>
            )}
          </div>
        </InfoWindow>
      )}
    </>
  )
}

export default function PantryMap({ pantries, userLocation, className }) {
  return (
    <div
      className={clsx(
        'relative overflow-hidden rounded-2xl',
        'border border-emerald-500/20',
        'shadow-[0_0_30px_rgba(16,185,129,0.1)]',
        'bg-zinc-900',
        className
      )}
    >
      {/* Glow effect on corners */}
      <div className="absolute -top-20 -left-20 w-40 h-40 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-20 -right-20 w-40 h-40 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

      <APIProvider apiKey={MAPS_KEY}>
        <Map
          defaultCenter={DEFAULT_CENTER}
          defaultZoom={DEFAULT_ZOOM}
          mapId="equitable-dark-map"
          gestureHandling="greedy"
          disableDefaultUI={false}
          styles={DARK_MAP_STYLE}
          className="w-full h-full"
        >
          <MapContent pantries={pantries} userLocation={userLocation} />
        </Map>
      </APIProvider>

      {/* Overlay gradient for depth */}
      <div className="absolute inset-0 pointer-events-none bg-gradient-to-t from-zinc-950/20 via-transparent to-transparent" />
    </div>
  )
}
