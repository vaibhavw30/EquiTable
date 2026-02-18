import { useState, useCallback, useRef, useEffect } from 'react'
import { startDiscovery, createDiscoveryStream } from '../services/discoveryService'

/**
 * Hook for live pantry discovery via SSE.
 *
 * Returns:
 * - discover(query, radiusMeters): start a discovery job
 * - cancel(): close the SSE stream
 * - isDiscovering: boolean
 * - discoveredPantries: array of pantries found so far
 * - progress: { found, total, failed, succeeded }
 * - error: string | null
 * - jobId: string | null
 */
export default function useDiscovery() {
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [discoveredPantries, setDiscoveredPantries] = useState([])
  const [progress, setProgress] = useState({ found: 0, total: 0, failed: 0, succeeded: 0 })
  const [error, setError] = useState(null)
  const [jobId, setJobId] = useState(null)

  const eventSourceRef = useRef(null)

  const cancel = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsDiscovering(false)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [])

  const discover = useCallback(async ({ query, lat, lng, radiusMeters = 8000 }) => {
    // Close any existing stream
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }

    // Reset state
    setIsDiscovering(true)
    setDiscoveredPantries([])
    setProgress({ found: 0, total: 0, failed: 0, succeeded: 0 })
    setError(null)
    setJobId(null)

    let response
    try {
      response = await startDiscovery({ query, lat, lng, radius_meters: radiusMeters })
    } catch (err) {
      const detail = err.response?.data?.detail || err.message
      setError(detail)
      setIsDiscovering(false)
      return
    }

    setJobId(response.job_id)

    // Open SSE stream
    const es = createDiscoveryStream(response.stream_url)
    eventSourceRef.current = es

    es.addEventListener('job_started', (e) => {
      try {
        const data = JSON.parse(e.data)
        setProgress((prev) => ({ ...prev, total: data.urls_found || 0 }))
      } catch { /* ignore parse errors */ }
    })

    es.addEventListener('pantry_discovered', (e) => {
      try {
        const pantry = JSON.parse(e.data)
        setDiscoveredPantries((prev) => [...prev, pantry])
        setProgress((prev) => ({
          ...prev,
          found: prev.found + 1,
          succeeded: prev.succeeded + 1,
        }))
      } catch { /* ignore parse errors */ }
    })

    es.addEventListener('pantry_failed', () => {
      setProgress((prev) => ({ ...prev, failed: prev.failed + 1 }))
    })

    es.addEventListener('pantry_skipped', () => {
      // Skipped pantries don't count as found or failed
    })

    es.addEventListener('progress', (e) => {
      try {
        const data = JSON.parse(e.data)
        setProgress((prev) => ({
          ...prev,
          total: data.total || prev.total,
          succeeded: data.succeeded ?? prev.succeeded,
          failed: data.failed ?? prev.failed,
        }))
      } catch { /* ignore parse errors */ }
    })

    es.addEventListener('complete', (e) => {
      try {
        const data = JSON.parse(e.data)
        setProgress((prev) => ({
          ...prev,
          found: data.found ?? prev.found,
          total: data.found + (data.failed || 0) + (data.skipped || 0),
          failed: data.failed ?? prev.failed,
          succeeded: data.found ?? prev.succeeded,
        }))
      } catch { /* ignore parse errors */ }
      es.close()
      eventSourceRef.current = null
      setIsDiscovering(false)
    })

    es.addEventListener('error_event', (e) => {
      try {
        const data = JSON.parse(e.data)
        setError(data.message || 'Discovery failed')
      } catch {
        setError('Discovery failed unexpectedly')
      }
      es.close()
      eventSourceRef.current = null
      setIsDiscovering(false)
    })

    // Handle native EventSource errors (network, etc.)
    es.onerror = () => {
      // EventSource auto-reconnects by default; if readyState is CLOSED,
      // it means the connection is dead
      if (es.readyState === EventSource.CLOSED) {
        setError('Connection to discovery stream lost')
        eventSourceRef.current = null
        setIsDiscovering(false)
      }
    }
  }, [])

  return {
    discover,
    cancel,
    isDiscovering,
    discoveredPantries,
    progress,
    error,
    jobId,
  }
}
