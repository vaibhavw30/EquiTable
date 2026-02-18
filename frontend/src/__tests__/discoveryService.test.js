import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'

vi.mock('axios')

// Import after mock
import { startDiscovery, getDiscoveryStatus, createDiscoveryStream } from '../services/discoveryService'

describe('discoveryService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('startDiscovery', () => {
    it('posts to /pantries/discover and returns response data', async () => {
      const mockResponse = {
        job_id: 'abc-123',
        status: 'running',
        stream_url: '/pantries/discover/stream/abc-123',
        existing_pantries: 2,
      }
      axios.post.mockResolvedValueOnce({ data: mockResponse })

      const result = await startDiscovery({
        query: 'Denver, CO',
        lat: 39.7392,
        lng: -104.9903,
        radius_meters: 8000,
      })

      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining('/pantries/discover'),
        {
          query: 'Denver, CO',
          lat: 39.7392,
          lng: -104.9903,
          radius_meters: 8000,
        }
      )
      expect(result).toEqual(mockResponse)
    })

    it('uses default radius_meters of 8000', async () => {
      axios.post.mockResolvedValueOnce({ data: { job_id: 'x' } })

      await startDiscovery({ query: 'Test', lat: 0, lng: 0 })

      expect(axios.post).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ radius_meters: 8000 })
      )
    })

    it('propagates HTTP errors', async () => {
      axios.post.mockRejectedValueOnce({
        response: { status: 429, data: { detail: 'Rate limit exceeded' } },
      })

      await expect(
        startDiscovery({ query: 'Test', lat: 0, lng: 0 })
      ).rejects.toBeTruthy()
    })
  })

  describe('getDiscoveryStatus', () => {
    it('fetches status for a given job ID', async () => {
      const mockStatus = { job_id: 'abc', status: 'completed', urls_found: 5 }
      axios.get.mockResolvedValueOnce({ data: mockStatus })

      const result = await getDiscoveryStatus('abc')

      expect(axios.get).toHaveBeenCalledWith(
        expect.stringContaining('/pantries/discover/status/abc')
      )
      expect(result).toEqual(mockStatus)
    })
  })

  describe('createDiscoveryStream', () => {
    it('creates an EventSource with the correct URL', () => {
      const mockES = { close: vi.fn() }
      globalThis.EventSource = vi.fn(function (url) {
        this.url = url
        this.close = mockES.close
      })

      const result = createDiscoveryStream('/pantries/discover/stream/abc')

      expect(globalThis.EventSource).toHaveBeenCalledWith(
        expect.stringContaining('/pantries/discover/stream/abc')
      )
      expect(result).toBeInstanceOf(EventSource)
    })
  })
})
