import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'

// Mock axios
const mockGet = vi.fn().mockResolvedValue({ data: [] })
vi.mock('axios', () => ({
  default: {
    get: (...args) => mockGet(...args),
  },
}))

import useMapLazyLoad from '../hooks/useMapLazyLoad'

describe('useMapLazyLoad', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('starts with isInView false', () => {
    const { result } = renderHook(() => useMapLazyLoad())
    expect(result.current.isInView).toBe(false)
  })

  it('provides an onBecomeVisible callback', () => {
    const { result } = renderHook(() => useMapLazyLoad())
    expect(typeof result.current.onBecomeVisible).toBe('function')
  })

  it('does not fetch pantries before onBecomeVisible is called', () => {
    renderHook(() => useMapLazyLoad())
    // usePantries is called with enabled=false, so no axios.get call
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('sets isInView to true when onBecomeVisible is called', () => {
    const { result } = renderHook(() => useMapLazyLoad())
    expect(result.current.isInView).toBe(false)

    act(() => {
      result.current.onBecomeVisible()
    })

    expect(result.current.isInView).toBe(true)
  })

  it('fetches pantries after onBecomeVisible is called', async () => {
    mockGet.mockResolvedValueOnce({ data: [{ _id: '1', name: 'Test' }] })

    const { result } = renderHook(() => useMapLazyLoad())

    act(() => {
      result.current.onBecomeVisible()
    })

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalled()
    })

    const callUrl = mockGet.mock.calls[0][0]
    expect(callUrl).toContain('/pantries')
  })

  it('returns pantries data after fetch', async () => {
    const pantryData = [
      { _id: '1', name: 'Pantry A' },
      { _id: '2', name: 'Pantry B' },
    ]
    mockGet.mockResolvedValueOnce({ data: pantryData })

    const { result } = renderHook(() => useMapLazyLoad())

    act(() => {
      result.current.onBecomeVisible()
    })

    await waitFor(() => {
      expect(result.current.pantries).toEqual(pantryData)
    })
  })

  it('returns loading state', async () => {
    mockGet.mockResolvedValueOnce({ data: [] })

    const { result } = renderHook(() => useMapLazyLoad())

    act(() => {
      result.current.onBecomeVisible()
    })

    // Should be loading after becoming visible
    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
  })

  it('returns error on fetch failure', async () => {
    mockGet.mockRejectedValueOnce(new Error('Network error'))

    const { result } = renderHook(() => useMapLazyLoad())

    act(() => {
      result.current.onBecomeVisible()
    })

    await waitFor(() => {
      expect(result.current.error).toBe('Network error')
    })
  })

  it('provides a refresh function', async () => {
    mockGet.mockResolvedValue({ data: [] })

    const { result } = renderHook(() => useMapLazyLoad())

    expect(typeof result.current.refresh).toBe('function')
  })
})
