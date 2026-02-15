import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'https://equitable.onrender.com'

export default function useNearbyPantries({ lat, lng, maxDistance, enabled = true }) {
  const [pantries, setPantries] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!enabled || lat == null || lng == null || maxDistance == null) {
      setPantries([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const { data } = await axios.get(`${API_BASE}/pantries/nearby`, {
        params: { lat, lng, max_distance: maxDistance, limit: 200 },
      })
      setPantries(data)
    } catch (err) {
      const msg = err.response
        ? `HTTP ${err.response.status}: ${err.response.statusText}`
        : err.message
      console.error('Failed to fetch nearby pantries:', msg)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [lat, lng, maxDistance, enabled])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { pantries, loading, error, refresh }
}
