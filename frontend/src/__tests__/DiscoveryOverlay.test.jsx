import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import DiscoveryOverlay from '../components/DiscoveryOverlay'

// Mock useReducedMotion
let mockReducedMotion = false
vi.mock('../hooks/useReducedMotion', () => ({
  default: () => mockReducedMotion,
}))

describe('DiscoveryOverlay', () => {
  beforeEach(() => {
    mockReducedMotion = false
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  const baseProps = {
    isDiscovering: false,
    discoveryDone: false,
    progress: { found: 0, total: 0, failed: 0, succeeded: 0 },
    error: null,
    query: 'Denver, CO',
    onCancel: vi.fn(),
    onDismiss: vi.fn(),
    onRetry: vi.fn(),
  }

  // ── DiscoveryLoader (in-progress state) ──

  describe('DiscoveryLoader', () => {
    it('renders with location name', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          isDiscovering={true}
        />
      )
      expect(screen.getByTestId('discovery-loader')).toBeInTheDocument()
      expect(screen.getByTestId('discovery-location')).toHaveTextContent(
        'Discovering pantries in Denver, CO...'
      )
    })

    it('renders without location when query is null', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          isDiscovering={true}
          query={null}
        />
      )
      expect(screen.getByTestId('discovery-location')).toHaveTextContent(
        'Discovering pantries...'
      )
    })

    it('shows progressive count as pantries are found', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          isDiscovering={true}
          progress={{ found: 3, total: 8, failed: 0, succeeded: 3 }}
        />
      )
      expect(screen.getByTestId('discovery-count')).toHaveTextContent(
        'Found 3 so far...'
      )
    })

    it('does not show count when no pantries found yet', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          isDiscovering={true}
          progress={{ found: 0, total: 8, failed: 0, succeeded: 0 }}
        />
      )
      expect(screen.queryByTestId('discovery-count')).not.toBeInTheDocument()
    })

    it('shows radar pulse animation', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          isDiscovering={true}
        />
      )
      expect(screen.getByTestId('radar-pulse')).toBeInTheDocument()
    })

    it('shows mobile bottom bar on small screens', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          isDiscovering={true}
        />
      )
      expect(screen.getByTestId('discovery-mobile-bar')).toBeInTheDocument()
    })
  })

  // ── Cancel ──

  describe('Cancel button', () => {
    it('triggers onCancel callback', () => {
      const onCancel = vi.fn()
      render(
        <DiscoveryOverlay
          {...baseProps}
          isDiscovering={true}
          onCancel={onCancel}
        />
      )

      fireEvent.click(screen.getByTestId('discovery-cancel'))
      expect(onCancel).toHaveBeenCalledTimes(1)
    })
  })

  // ── Toast states ──

  describe('DiscoveryToast', () => {
    it('shows success message with count', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          discoveryDone={true}
          progress={{ found: 5, total: 5, failed: 0, succeeded: 5 }}
        />
      )
      expect(screen.getByTestId('toast-message')).toHaveTextContent(
        'Found 5 pantries near Denver, CO'
      )
    })

    it('shows partial failure message', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          discoveryDone={true}
          progress={{ found: 0, total: 5, failed: 5, succeeded: 0 }}
        />
      )
      expect(screen.getByTestId('toast-message')).toHaveTextContent(
        "Some pantries couldn't be loaded"
      )
    })

    it('shows empty state message', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          discoveryDone={true}
          progress={{ found: 0, total: 0, failed: 0, succeeded: 0 }}
        />
      )
      expect(screen.getByTestId('toast-message')).toHaveTextContent(
        'No pantries found in Denver, CO'
      )
    })

    it('shows error message', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          discoveryDone={true}
          error="Rate limit exceeded"
        />
      )
      expect(screen.getByTestId('toast-message')).toHaveTextContent(
        'Rate limit exceeded'
      )
    })

    it('shows retry button on error', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          discoveryDone={true}
          error="Failed"
        />
      )
      expect(screen.getByTestId('toast-retry')).toBeInTheDocument()
    })

    it('shows retry button on partial failure', () => {
      render(
        <DiscoveryOverlay
          {...baseProps}
          discoveryDone={true}
          progress={{ found: 0, total: 5, failed: 5, succeeded: 0 }}
        />
      )
      expect(screen.getByTestId('toast-retry')).toBeInTheDocument()
    })

    it('dismiss button triggers onDismiss', () => {
      const onDismiss = vi.fn()
      render(
        <DiscoveryOverlay
          {...baseProps}
          discoveryDone={true}
          progress={{ found: 5, total: 5, failed: 0, succeeded: 5 }}
          onDismiss={onDismiss}
        />
      )

      fireEvent.click(screen.getByTestId('toast-dismiss'))
      expect(onDismiss).toHaveBeenCalledTimes(1)
    })

    it('auto-dismisses success after 5 seconds', () => {
      const onDismiss = vi.fn()
      render(
        <DiscoveryOverlay
          {...baseProps}
          discoveryDone={true}
          progress={{ found: 3, total: 3, failed: 0, succeeded: 3 }}
          onDismiss={onDismiss}
        />
      )

      // Should still be visible
      expect(screen.getByTestId('toast-message')).toBeInTheDocument()

      // Advance past 5s
      act(() => {
        vi.advanceTimersByTime(5100)
      })

      expect(onDismiss).toHaveBeenCalled()
    })
  })

  // ── Reduced motion ──

  describe('Reduced motion', () => {
    it('replaces radar animation with text indicator', () => {
      mockReducedMotion = true
      render(
        <DiscoveryOverlay
          {...baseProps}
          isDiscovering={true}
        />
      )

      expect(screen.getByTestId('radar-reduced')).toBeInTheDocument()
      expect(screen.getByText('Searching...')).toBeInTheDocument()
      expect(screen.queryByTestId('radar-pulse')).not.toBeInTheDocument()
    })

    it('shows radar pulse when motion is not reduced', () => {
      mockReducedMotion = false
      render(
        <DiscoveryOverlay
          {...baseProps}
          isDiscovering={true}
        />
      )

      expect(screen.getByTestId('radar-pulse')).toBeInTheDocument()
      expect(screen.queryByTestId('radar-reduced')).not.toBeInTheDocument()
    })
  })

  // ── Hidden when not active ──

  describe('Hidden state', () => {
    it('renders nothing when not discovering and not done', () => {
      const { container } = render(
        <DiscoveryOverlay {...baseProps} />
      )
      // Should have no visible children (AnimatePresence may render empty wrappers)
      expect(screen.queryByTestId('discovery-loader')).not.toBeInTheDocument()
      expect(screen.queryByTestId('discovery-toast')).not.toBeInTheDocument()
    })
  })
})
