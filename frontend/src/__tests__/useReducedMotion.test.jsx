import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Don't mock the hook — test the real implementation
import useReducedMotion from '../hooks/useReducedMotion'

describe('useReducedMotion', () => {
  let matchMediaListeners = []
  let matchMediaMatches = false

  beforeEach(() => {
    matchMediaListeners = []
    matchMediaMatches = false

    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: matchMediaMatches,
      media: query,
      addEventListener: vi.fn((event, handler) => {
        matchMediaListeners.push(handler)
      }),
      removeEventListener: vi.fn(),
    }))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns false when motion is not reduced', () => {
    matchMediaMatches = false
    const { result } = renderHook(() => useReducedMotion())
    expect(result.current).toBe(false)
  })

  it('returns true when motion is reduced', () => {
    matchMediaMatches = true
    const { result } = renderHook(() => useReducedMotion())
    expect(result.current).toBe(true)
  })

  it('queries the correct media query', () => {
    renderHook(() => useReducedMotion())
    expect(window.matchMedia).toHaveBeenCalledWith('(prefers-reduced-motion: reduce)')
  })

  it('updates when preference changes', () => {
    matchMediaMatches = false
    const { result } = renderHook(() => useReducedMotion())
    expect(result.current).toBe(false)

    // Simulate preference change
    act(() => {
      matchMediaListeners.forEach((handler) => handler({ matches: true }))
    })

    expect(result.current).toBe(true)
  })
})
