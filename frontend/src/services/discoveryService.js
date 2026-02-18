import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'https://equitable.onrender.com'

/**
 * Start a discovery job for food pantries near a location.
 * @param {{ query: string, lat: number, lng: number, radius_meters?: number }} params
 * @returns {Promise<{ job_id: string, status: string, stream_url: string, existing_pantries: number }>}
 */
export async function startDiscovery({ query, lat, lng, radius_meters = 8000 }) {
  const { data } = await axios.post(`${API_BASE}/pantries/discover`, {
    query,
    lat,
    lng,
    radius_meters,
  })
  return data
}

/**
 * Get the current status of a discovery job (polling fallback).
 * @param {string} jobId
 * @returns {Promise<object>}
 */
export async function getDiscoveryStatus(jobId) {
  const { data } = await axios.get(`${API_BASE}/pantries/discover/status/${jobId}`)
  return data
}

/**
 * Create an EventSource for streaming discovery events.
 * @param {string} streamUrl - relative URL like "/pantries/discover/stream/{job_id}"
 * @returns {EventSource}
 */
export function createDiscoveryStream(streamUrl) {
  return new EventSource(`${API_BASE}${streamUrl}`)
}

export { API_BASE }
