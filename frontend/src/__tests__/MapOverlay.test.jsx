import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Mock Google Maps
vi.mock('@vis.gl/react-google-maps', () => ({
  APIProvider: ({ children }) => <div data-testid="mock-api-provider">{children}</div>,
  Map: ({ children }) => <div data-testid="mock-map">{children}</div>,
  AdvancedMarker: ({ children }) => <div data-testid="mock-marker">{children}</div>,
  InfoWindow: ({ children }) => <div>{children}</div>,
  Pin: () => <div data-testid="mock-pin" />,
  useMap: () => null,
  MapControl: ({ children }) => <div data-testid="mock-map-control">{children}</div>,
  ControlPosition: { TOP: 'TOP' },
  useMapsLibrary: () => null,
}))

// Mock axios
vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
  },
}))

// Mock useReducedMotion
vi.mock('../hooks/useReducedMotion', () => ({
  default: () => false,
}))

import MapOverlay from '../components/MapOverlay'

describe('MapOverlay', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.documentElement.style.overflow = ''
  })

  afterEach(() => {
    document.documentElement.style.overflow = ''
  })

  it('renders nothing when closed', () => {
    render(
      <MemoryRouter>
        <MapOverlay isOpen={false} onClose={() => {}} />
      </MemoryRouter>
    )
    expect(screen.queryByTestId('map-overlay')).not.toBeInTheDocument()
  })

  it('renders overlay when open', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapOverlay isOpen={true} onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(screen.getByTestId('map-overlay')).toBeInTheDocument()
  })

  it('has a close button', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapOverlay isOpen={true} onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(screen.getByTestId('close-map-overlay')).toBeInTheDocument()
  })

  it('calls onClose when close button clicked', async () => {
    const onClose = vi.fn()
    await act(async () => {
      render(
        <MemoryRouter>
          <MapOverlay isOpen={true} onClose={onClose} />
        </MemoryRouter>
      )
    })
    await act(async () => {
      fireEvent.click(screen.getByTestId('close-map-overlay'))
    })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose on ESC key', async () => {
    const onClose = vi.fn()
    await act(async () => {
      render(
        <MemoryRouter>
          <MapOverlay isOpen={true} onClose={onClose} />
        </MemoryRouter>
      )
    })
    await act(async () => {
      fireEvent.keyDown(document, { key: 'Escape' })
    })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('locks body scroll when open', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapOverlay isOpen={true} onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(document.documentElement.style.overflow).toBe('hidden')
  })

  it('has dialog role and aria attributes', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapOverlay isOpen={true} onClose={() => {}} />
        </MemoryRouter>
      )
    })
    const overlay = screen.getByTestId('map-overlay')
    expect(overlay).toHaveAttribute('role', 'dialog')
    expect(overlay).toHaveAttribute('aria-modal', 'true')
    expect(overlay).toHaveAttribute('aria-label', 'Full map experience')
  })

  it('close button has aria-label', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapOverlay isOpen={true} onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(screen.getByTestId('close-map-overlay')).toHaveAttribute('aria-label', 'Close map')
  })
})
