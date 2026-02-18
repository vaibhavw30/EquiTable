import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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

// Control useInView per test
let mockInView = true
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion')
  return {
    ...actual,
    useInView: () => mockInView,
  }
})

// Mock useReducedMotion
vi.mock('../hooks/useReducedMotion', () => ({
  default: () => false,
}))

import MapPreviewSection from '../components/MapPreviewSection'

const mockPantries = [
  { _id: '1', name: 'Test Pantry', address: '123 Main St', lat: 33.78, lng: -84.40, status: 'OPEN' },
]

describe('MapPreviewSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockInView = true
  })

  it('renders the section', () => {
    render(
      <MemoryRouter>
        <MapPreviewSection isInView={true} onBecomeVisible={() => {}} pantries={mockPantries} onExpand={() => {}} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('map-preview-section')).toBeInTheDocument()
  })

  it('renders the section header', () => {
    render(
      <MemoryRouter>
        <MapPreviewSection isInView={true} onBecomeVisible={() => {}} pantries={mockPantries} onExpand={() => {}} />
      </MemoryRouter>
    )
    expect(screen.getByText('Explore Food Pantries Near You')).toBeInTheDocument()
  })

  it('renders map when in view', () => {
    render(
      <MemoryRouter>
        <MapPreviewSection isInView={true} onBecomeVisible={() => {}} pantries={mockPantries} onExpand={() => {}} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('mock-api-provider')).toBeInTheDocument()
    expect(screen.queryByTestId('map-skeleton')).not.toBeInTheDocument()
  })

  it('renders skeleton when not in view', () => {
    mockInView = false
    render(
      <MemoryRouter>
        <MapPreviewSection isInView={false} onBecomeVisible={() => {}} pantries={[]} onExpand={() => {}} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('map-skeleton')).toBeInTheDocument()
    expect(screen.queryByTestId('mock-api-provider')).not.toBeInTheDocument()
  })

  it('shows expand button when in view', () => {
    render(
      <MemoryRouter>
        <MapPreviewSection isInView={true} onBecomeVisible={() => {}} pantries={mockPantries} onExpand={() => {}} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('expand-map-button')).toBeInTheDocument()
    expect(screen.getByText('Explore Full Map')).toBeInTheDocument()
  })

  it('calls onExpand when expand button is clicked', () => {
    const onExpand = vi.fn()
    render(
      <MemoryRouter>
        <MapPreviewSection isInView={true} onBecomeVisible={() => {}} pantries={mockPantries} onExpand={onExpand} />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('expand-map-button'))
    expect(onExpand).toHaveBeenCalledTimes(1)
  })

  it('shows cooperative mode hint when in view', () => {
    render(
      <MemoryRouter>
        <MapPreviewSection isInView={true} onBecomeVisible={() => {}} pantries={mockPantries} onExpand={() => {}} />
      </MemoryRouter>
    )
    expect(screen.getByText('Use two fingers to zoom')).toBeInTheDocument()
  })

  it('calls onBecomeVisible when IntersectionObserver fires', () => {
    const onBecomeVisible = vi.fn()
    mockInView = true // simulate intersection observer triggering
    render(
      <MemoryRouter>
        <MapPreviewSection isInView={false} onBecomeVisible={onBecomeVisible} pantries={[]} onExpand={() => {}} />
      </MemoryRouter>
    )
    expect(onBecomeVisible).toHaveBeenCalledTimes(1)
  })
})
