import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useViewportDiscovery from '../hooks/useViewportDiscovery'

function createMockMap(center = { lat: 33.78, lng: -84.40 }, bounds = null) {
  const ne = { lat: () => center.lat + 0.05, lng: () => center.lng + 0.05 }
  const sw = { lat: () => center.lat - 0.05, lng: () => center.lng - 0.05 }
  return {
    getCenter: () => ({
      lat: () => center.lat,
      lng: () => center.lng,
    }),
    getBounds: () =>
      bounds || {
        getNorthEast: () => ne,
        getSouthWest: () => sw,
      },
  }
}

describe('useViewportDiscovery', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('triggers discovery when few pantries in viewport', () => {
    const discover = vi.fn()
    const { result } = renderHook(() =>
      useViewportDiscovery({ pantries: [], discover, isDiscovering: false })
    )

    const mockMap = createMockMap()
    act(() => {
      result.current.onMapIdle(mockMap)
    })

    // Advance past debounce
    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(discover).toHaveBeenCalledTimes(1)
    expect(discover).toHaveBeenCalledWith(
      expect.objectContaining({
        lat: 33.78,
        lng: -84.40,
        query: 'food pantry',
      })
    )
  })

  it('does NOT trigger discovery when enough pantries in viewport', () => {
    const discover = vi.fn()
    const pantries = [
      { lat: 33.78, lng: -84.40 },
      { lat: 33.79, lng: -84.39 },
      { lat: 33.77, lng: -84.41 },
    ]
    const { result } = renderHook(() =>
      useViewportDiscovery({ pantries, discover, isDiscovering: false })
    )

    const mockMap = createMockMap()
    act(() => {
      result.current.onMapIdle(mockMap)
    })

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(discover).not.toHaveBeenCalled()
  })

  it('does NOT trigger when already discovering', () => {
    const discover = vi.fn()
    const { result } = renderHook(() =>
      useViewportDiscovery({ pantries: [], discover, isDiscovering: true })
    )

    const mockMap = createMockMap()
    act(() => {
      result.current.onMapIdle(mockMap)
    })

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(discover).not.toHaveBeenCalled()
  })

  it('deduplicates when center has not moved significantly', () => {
    const discover = vi.fn()
    const { result } = renderHook(() =>
      useViewportDiscovery({ pantries: [], discover, isDiscovering: false })
    )

    const mockMap = createMockMap()

    // First idle — triggers discovery
    act(() => {
      result.current.onMapIdle(mockMap)
    })
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(discover).toHaveBeenCalledTimes(1)

    // Second idle at same location — should NOT trigger
    act(() => {
      result.current.onMapIdle(mockMap)
    })
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(discover).toHaveBeenCalledTimes(1)
  })

  it('triggers again when center moves significantly', () => {
    const discover = vi.fn()
    const { result } = renderHook(() =>
      useViewportDiscovery({ pantries: [], discover, isDiscovering: false })
    )

    // First location
    act(() => {
      result.current.onMapIdle(createMockMap({ lat: 33.78, lng: -84.40 }))
    })
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(discover).toHaveBeenCalledTimes(1)

    // Move > 2km away
    act(() => {
      result.current.onMapIdle(createMockMap({ lat: 34.00, lng: -84.40 }))
    })
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(discover).toHaveBeenCalledTimes(2)
  })

  it('debounces rapid idle events', () => {
    const discover = vi.fn()
    const { result } = renderHook(() =>
      useViewportDiscovery({ pantries: [], discover, isDiscovering: false })
    )

    const mockMap = createMockMap()

    // Rapid fire idle events
    act(() => {
      result.current.onMapIdle(mockMap)
    })
    act(() => {
      vi.advanceTimersByTime(500)
    })
    act(() => {
      result.current.onMapIdle(mockMap)
    })
    act(() => {
      vi.advanceTimersByTime(500)
    })
    act(() => {
      result.current.onMapIdle(mockMap)
    })

    // Only after final debounce should it fire
    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(discover).toHaveBeenCalledTimes(1)
  })
})
