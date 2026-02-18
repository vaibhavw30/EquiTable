import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import useDiscovery from '../hooks/useDiscovery'

// Mock the service module
vi.mock('../services/discoveryService', () => ({
  startDiscovery: vi.fn(),
  createDiscoveryStream: vi.fn(),
}))

import { startDiscovery, createDiscoveryStream } from '../services/discoveryService'

// Helper to create a mock EventSource
function createMockEventSource() {
  const listeners = {}
  return {
    addEventListener: vi.fn((event, cb) => {
      listeners[event] = cb
    }),
    close: vi.fn(),
    readyState: 0, // CONNECTING
    // Helpers for tests
    _listeners: listeners,
    _emit(event, data) {
      if (listeners[event]) {
        listeners[event]({ data: JSON.stringify(data) })
      }
    },
  }
}

describe('useDiscovery', () => {
  let mockES

  beforeEach(() => {
    vi.clearAllMocks()
    mockES = createMockEventSource()
    createDiscoveryStream.mockReturnValue(mockES)
  })

  it('starts in idle state', () => {
    const { result } = renderHook(() => useDiscovery())

    expect(result.current.isDiscovering).toBe(false)
    expect(result.current.discoveredPantries).toEqual([])
    expect(result.current.progress).toEqual({ found: 0, total: 0, failed: 0, succeeded: 0 })
    expect(result.current.error).toBeNull()
    expect(result.current.jobId).toBeNull()
  })

  it('sets isDiscovering to true and creates EventSource on discover()', async () => {
    startDiscovery.mockResolvedValueOnce({
      job_id: 'test-job',
      stream_url: '/pantries/discover/stream/test-job',
    })

    const { result } = renderHook(() => useDiscovery())

    await act(async () => {
      await result.current.discover({ query: 'Denver', lat: 39.7, lng: -104.9 })
    })

    expect(result.current.isDiscovering).toBe(true)
    expect(result.current.jobId).toBe('test-job')
    expect(createDiscoveryStream).toHaveBeenCalledWith('/pantries/discover/stream/test-job')
  })

  it('accumulates pantries from pantry_discovered events', async () => {
    startDiscovery.mockResolvedValueOnce({
      job_id: 'j1',
      stream_url: '/stream/j1',
    })

    const { result } = renderHook(() => useDiscovery())

    await act(async () => {
      await result.current.discover({ query: 'Test', lat: 0, lng: 0 })
    })

    act(() => {
      mockES._emit('pantry_discovered', {
        _id: 'p1',
        name: 'Food Bank A',
        lat: 39.7,
        lng: -104.9,
      })
    })

    expect(result.current.discoveredPantries).toHaveLength(1)
    expect(result.current.discoveredPantries[0].name).toBe('Food Bank A')
    expect(result.current.progress.succeeded).toBe(1)

    act(() => {
      mockES._emit('pantry_discovered', {
        _id: 'p2',
        name: 'Food Bank B',
        lat: 39.8,
        lng: -104.8,
      })
    })

    expect(result.current.discoveredPantries).toHaveLength(2)
    expect(result.current.progress.succeeded).toBe(2)
  })

  it('tracks failures from pantry_failed events', async () => {
    startDiscovery.mockResolvedValueOnce({ job_id: 'j1', stream_url: '/s/j1' })

    const { result } = renderHook(() => useDiscovery())

    await act(async () => {
      await result.current.discover({ query: 'Test', lat: 0, lng: 0 })
    })

    act(() => {
      mockES._emit('pantry_failed', { source_url: 'https://fail.com', reason: 'timeout' })
    })

    expect(result.current.progress.failed).toBe(1)
  })

  it('updates total from job_started event', async () => {
    startDiscovery.mockResolvedValueOnce({ job_id: 'j1', stream_url: '/s/j1' })

    const { result } = renderHook(() => useDiscovery())

    await act(async () => {
      await result.current.discover({ query: 'Test', lat: 0, lng: 0 })
    })

    act(() => {
      mockES._emit('job_started', { job_id: 'j1', urls_found: 8 })
    })

    expect(result.current.progress.total).toBe(8)
  })

  it('closes EventSource and sets isDiscovering=false on complete', async () => {
    startDiscovery.mockResolvedValueOnce({ job_id: 'j1', stream_url: '/s/j1' })

    const { result } = renderHook(() => useDiscovery())

    await act(async () => {
      await result.current.discover({ query: 'Test', lat: 0, lng: 0 })
    })

    act(() => {
      mockES._emit('complete', { found: 3, failed: 1, skipped: 0 })
    })

    expect(mockES.close).toHaveBeenCalled()
    expect(result.current.isDiscovering).toBe(false)
    expect(result.current.progress.succeeded).toBe(3)
  })

  it('handles POST failure gracefully', async () => {
    startDiscovery.mockRejectedValueOnce({
      response: { data: { detail: 'Rate limit exceeded' } },
    })

    const { result } = renderHook(() => useDiscovery())

    await act(async () => {
      await result.current.discover({ query: 'Test', lat: 0, lng: 0 })
    })

    expect(result.current.isDiscovering).toBe(false)
    expect(result.current.error).toBe('Rate limit exceeded')
  })

  it('cancel() closes EventSource and resets isDiscovering', async () => {
    startDiscovery.mockResolvedValueOnce({ job_id: 'j1', stream_url: '/s/j1' })

    const { result } = renderHook(() => useDiscovery())

    await act(async () => {
      await result.current.discover({ query: 'Test', lat: 0, lng: 0 })
    })

    expect(result.current.isDiscovering).toBe(true)

    act(() => {
      result.current.cancel()
    })

    expect(mockES.close).toHaveBeenCalled()
    expect(result.current.isDiscovering).toBe(false)
  })

  it('cleans up EventSource on unmount', async () => {
    startDiscovery.mockResolvedValueOnce({ job_id: 'j1', stream_url: '/s/j1' })

    const { result, unmount } = renderHook(() => useDiscovery())

    await act(async () => {
      await result.current.discover({ query: 'Test', lat: 0, lng: 0 })
    })

    unmount()
    expect(mockES.close).toHaveBeenCalled()
  })

  it('resets state when starting a new discovery', async () => {
    startDiscovery.mockResolvedValue({ job_id: 'j2', stream_url: '/s/j2' })

    const { result } = renderHook(() => useDiscovery())

    // First discovery
    await act(async () => {
      await result.current.discover({ query: 'City A', lat: 0, lng: 0 })
    })

    act(() => {
      mockES._emit('pantry_discovered', { _id: 'p1', name: 'Pantry 1' })
    })

    expect(result.current.discoveredPantries).toHaveLength(1)

    // Create a fresh mock for the second call
    const mockES2 = createMockEventSource()
    createDiscoveryStream.mockReturnValue(mockES2)

    // Second discovery — should reset
    await act(async () => {
      await result.current.discover({ query: 'City B', lat: 1, lng: 1 })
    })

    expect(result.current.discoveredPantries).toHaveLength(0)
    expect(result.current.progress).toEqual({ found: 0, total: 0, failed: 0, succeeded: 0 })
  })
})
