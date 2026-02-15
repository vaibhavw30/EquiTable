import { useState, useCallback, useEffect, useRef } from 'react'
import {
  APIProvider,
  Map,
  AdvancedMarker,
  InfoWindow,
  Pin,
  useMap,
} from '@vis.gl/react-google-maps'
import { Clock, Shield, MapPin } from 'lucide-react'
import { clsx } from 'clsx'

const MAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY

// Atlanta default center
const DEFAULT_CENTER = { lat: 33.78, lng: -84.40 }
const DEFAULT_ZOOM = 12

// Clean, subtle map style (light theme with muted colors)
const CLEAN_MAP_STYLE = [
  {
    featureType: 'poi',
    elementType: 'labels',
    stylers: [{ visibility: 'off' }],
  },
  {
    featureType: 'poi.business',
    stylers: [{ visibility: 'off' }],
  },
  {
    featureType: 'road',
    elementType: 'labels.icon',
    stylers: [{ visibility: 'off' }],
  },
  {
    featureType: 'transit',
    stylers: [{ visibility: 'off' }],
  },
  {
    featureType: 'water',
    elementType: 'geometry.fill',
    stylers: [{ color: '#c9e4f4' }],
  },
  {
    featureType: 'landscape.natural',
    elementType: 'geometry.fill',
    stylers: [{ color: '#f5f5f5' }],
  },
  {
    featureType: 'road.highway',
    elementType: 'geometry.fill',
    stylers: [{ color: '#ffffff' }],
  },
  {
    featureType: 'road.highway',
    elementType: 'geometry.stroke',
    stylers: [{ color: '#e5e5e5' }],
  },
  {
    featureType: 'road.arterial',
    elementType: 'geometry.fill',
    stylers: [{ color: '#ffffff' }],
  },
  {
    featureType: 'road.local',
    elementType: 'geometry.fill',
    stylers: [{ color: '#ffffff' }],
  },
]

/**
 * 4-color pin logic:
 * - CLOSED → Red
 * - UNKNOWN or WAITLIST → Gray
 * - OPEN + ID required → Amber
 * - OPEN + no ID → Green
 */
function markerColors(pantry) {
  if (pantry.status === 'CLOSED') {
    return { background: '#EF4444', glyphColor: '#fff', borderColor: '#DC2626' }
  }
  if (pantry.status === 'UNKNOWN' || pantry.status === 'WAITLIST') {
    return { background: '#9CA3AF', glyphColor: '#fff', borderColor: '#6B7280' }
  }
  if (pantry.is_id_required) {
    return { background: '#F59E0B', glyphColor: '#fff', borderColor: '#D97706' }
  }
  return { background: '#22C55E', glyphColor: '#fff', borderColor: '#16A34A' }
}

// Radius circle overlay using raw google.maps.Circle
function RadiusCircle({ center, radius }) {
  const map = useMap()
  const circleRef = useRef(null)

  useEffect(() => {
    if (!map || !center || !radius) {
      if (circleRef.current) {
        circleRef.current.setMap(null)
        circleRef.current = null
      }
      return
    }

    if (!circleRef.current) {
      circleRef.current = new google.maps.Circle({
        map,
        center,
        radius,
        fillColor: '#10B981',
        fillOpacity: 0.06,
        strokeColor: '#10B981',
        strokeOpacity: 0.3,
        strokeWeight: 1.5,
        clickable: false,
      })
    } else {
      circleRef.current.setCenter(center)
      circleRef.current.setRadius(radius)
      circleRef.current.setMap(map)
    }

    return () => {
      if (circleRef.current) {
        circleRef.current.setMap(null)
        circleRef.current = null
      }
    }
  }, [map, center, radius])

  return null
}

// Inner component to access map instance
function MapContent({ pantries, userLocation, selectedPantry, onPantrySelect, center, zoom, radiusCenter, radiusMeters }) {
  const map = useMap()
  const [infoWindowPantry, setInfoWindowPantry] = useState(null)

  const handleMarkerClick = useCallback((pantry) => {
    setInfoWindowPantry(pantry)
    onPantrySelect?.(pantry)
  }, [onPantrySelect])

  // Pan to center and optionally set zoom
  useEffect(() => {
    if (center && map) {
      map.panTo(center)
      map.setZoom(zoom || DEFAULT_ZOOM)
    }
  }, [center, zoom, map])

  // Pan to user location when it changes
  useEffect(() => {
    if (userLocation && map) {
      map.panTo(userLocation)
      if (!zoom) map.setZoom(14)
    }
  }, [userLocation, map])

  // Pan to selected pantry
  useEffect(() => {
    if (selectedPantry && map) {
      map.panTo({ lat: selectedPantry.lat, lng: selectedPantry.lng })
    }
  }, [selectedPantry, map])

  return (
    <>
      {/* Radius circle overlay */}
      <RadiusCircle center={radiusCenter} radius={radiusMeters} />

      {/* Pantry markers */}
      {pantries.map((pantry) => {
        const colors = markerColors(pantry)
        const isSelected = selectedPantry?._id === pantry._id

        return (
          <AdvancedMarker
            key={pantry._id}
            position={{ lat: pantry.lat, lng: pantry.lng }}
            onClick={() => handleMarkerClick(pantry)}
            zIndex={isSelected ? 100 : 1}
          >
            <Pin
              background={colors.background}
              glyphColor={colors.glyphColor}
              borderColor={isSelected ? '#000' : colors.borderColor}
              scale={isSelected ? 1.2 : 1}
            />
          </AdvancedMarker>
        )
      })}

      {/* User location marker (blue dot) */}
      {userLocation && (
        <AdvancedMarker position={userLocation} zIndex={200}>
          <div className="relative">
            <div className="w-4 h-4 bg-blue-500 rounded-full border-2 border-white shadow-lg" />
            <div className="absolute inset-0 w-4 h-4 bg-blue-500 rounded-full animate-ping opacity-40" />
          </div>
        </AdvancedMarker>
      )}

      {/* Minimal InfoWindow on marker click */}
      {infoWindowPantry && (
        <InfoWindow
          position={{ lat: infoWindowPantry.lat, lng: infoWindowPantry.lng }}
          onCloseClick={() => setInfoWindowPantry(null)}
          pixelOffset={[0, -40]}
        >
          <div className="p-2 max-w-[200px]">
            <h3 className="font-semibold text-zinc-900 text-sm mb-1">
              {infoWindowPantry.name}
            </h3>

            {infoWindowPantry.hours_today && (
              <div className="flex items-center gap-1 text-xs text-zinc-600 mb-1">
                <Clock className="w-3 h-3" />
                <span>{infoWindowPantry.hours_today}</span>
              </div>
            )}

            <div className="flex items-center gap-1 text-xs">
              <Shield className="w-3 h-3" />
              <span className={infoWindowPantry.is_id_required ? 'text-amber-600' : 'text-green-600'}>
                {infoWindowPantry.is_id_required ? 'ID Required' : 'No ID Required'}
              </span>
            </div>
          </div>
        </InfoWindow>
      )}
    </>
  )
}

export default function PantryMapClean({
  pantries,
  userLocation,
  selectedPantry,
  onPantrySelect,
  center,
  radiusCenter,
  radiusMeters,
  zoom,
  className,
}) {
  const mapCenter = center || DEFAULT_CENTER

  return (
    <div className={clsx('bg-zinc-100', className)}>
      <APIProvider apiKey={MAPS_KEY}>
        <Map
          defaultCenter={mapCenter}
          defaultZoom={DEFAULT_ZOOM}
          mapId="equitable-clean-map"
          gestureHandling="greedy"
          disableDefaultUI={false}
          styles={CLEAN_MAP_STYLE}
          className="w-full h-full"
        >
          <MapContent
            pantries={pantries}
            userLocation={userLocation}
            selectedPantry={selectedPantry}
            onPantrySelect={onPantrySelect}
            center={mapCenter}
            zoom={zoom}
            radiusCenter={radiusCenter}
            radiusMeters={radiusMeters}
          />
        </Map>
      </APIProvider>
    </div>
  )
}
