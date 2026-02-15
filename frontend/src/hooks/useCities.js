import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'https://equitable.onrender.com'

export default function useCities() {
  const [cities, setCities] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await axios.get(`${API_BASE}/cities`)
      setCities(data)
    } catch (err) {
      const msg = err.response
        ? `HTTP ${err.response.status}: ${err.response.statusText}`
        : err.message
      console.error('Failed to fetch cities:', msg)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { cities, loading, error, refresh }
}
