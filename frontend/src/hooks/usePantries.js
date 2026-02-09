import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

// Use environment variable for API URL, fallback to localhost for development
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export default function usePantries() {
  const [pantries, setPantries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await axios.get(`${API_BASE}/pantries`)
      setPantries(data)
    } catch (err) {
      const msg = err.response
        ? `HTTP ${err.response.status}: ${err.response.statusText}`
        : err.message
      console.error('Failed to fetch pantries:', msg)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { pantries, loading, error, refresh }
}
