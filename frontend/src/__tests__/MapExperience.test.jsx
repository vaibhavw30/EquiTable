import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
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

import MapExperience from '../components/MapExperience'

describe('MapExperience', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without crashing', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapExperience onClose={() => {}} />
        </MemoryRouter>
      )
    })
  })

  it('renders the sidebar with EquiTable branding', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapExperience onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(screen.getByText('EquiTable')).toBeInTheDocument()
  })

  it('renders the filter input', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapExperience onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(screen.getByPlaceholderText('Filter pantries...')).toBeInTheDocument()
  })

  it('renders filter chips', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapExperience onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(screen.getByText('Open Now')).toBeInTheDocument()
    expect(screen.getByText('No ID')).toBeInTheDocument()
  })

  it('renders the Google Maps mock', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapExperience onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(screen.getByTestId('mock-api-provider')).toBeInTheDocument()
  })

  it('renders the map legend', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapExperience onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('ID Req')).toBeInTheDocument()
    expect(screen.getByText('Closed')).toBeInTheDocument()
  })

  it('renders Near Me button', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <MapExperience onClose={() => {}} />
        </MemoryRouter>
      )
    })
    expect(screen.getByText('Near Me')).toBeInTheDocument()
  })

  it('calls onClose when EquiTable logo is clicked', async () => {
    const onClose = vi.fn()
    await act(async () => {
      render(
        <MemoryRouter>
          <MapExperience onClose={onClose} />
        </MemoryRouter>
      )
    })
    // The EquiTable button in sidebar calls onClose
    const equiTableButton = screen.getByText('EquiTable').closest('button')
    await act(async () => {
      equiTableButton.click()
    })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
