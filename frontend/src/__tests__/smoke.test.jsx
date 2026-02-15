/**
 * Smoke tests — these must pass before any merge.
 * They verify core pages render without crashing.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Mock Google Maps API — PantryMapClean uses @vis.gl/react-google-maps
vi.mock('@vis.gl/react-google-maps', () => ({
  APIProvider: ({ children }) => <div data-testid="mock-api-provider">{children}</div>,
  Map: ({ children }) => <div data-testid="mock-map">{children}</div>,
  AdvancedMarker: ({ children }) => <div data-testid="mock-marker">{children}</div>,
  InfoWindow: ({ children }) => <div>{children}</div>,
  Pin: () => <div data-testid="mock-pin" />,
  useMap: () => null,
}))

// Mock axios — usePantries calls axios.get on mount
vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn(),
    create: vi.fn(),
  },
}))

// Import pages after mocks are set up
import LandingPage from '../pages/LandingPage'
import MapPage from '../pages/MapPage'

describe('Smoke Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Landing Page', () => {
    it('renders without crashing', () => {
      render(
        <MemoryRouter>
          <LandingPage />
        </MemoryRouter>
      )
    })

    it('displays the app name', () => {
      render(
        <MemoryRouter>
          <LandingPage />
        </MemoryRouter>
      )
      expect(screen.getByText('EQUI')).toBeInTheDocument()
      expect(screen.getByText('TABLE')).toBeInTheDocument()
    })

    it('displays the tagline', () => {
      render(
        <MemoryRouter>
          <LandingPage />
        </MemoryRouter>
      )
      expect(
        screen.getByText('The Intelligence Layer for Food Security')
      ).toBeInTheDocument()
    })

    it('has a link to the map page', () => {
      render(
        <MemoryRouter>
          <LandingPage />
        </MemoryRouter>
      )
      expect(screen.getByText('LAUNCH SYSTEM')).toBeInTheDocument()
    })
  })

  describe('Map Page', () => {
    it('renders without crashing', async () => {
      await act(async () => {
        render(
          <MemoryRouter>
            <MapPage />
          </MemoryRouter>
        )
      })
    })

    it('displays the EquiTable branding', async () => {
      await act(async () => {
        render(
          <MemoryRouter>
            <MapPage />
          </MemoryRouter>
        )
      })
      expect(screen.getByText('EquiTable')).toBeInTheDocument()
    })

    it('renders the Google Maps mock', async () => {
      await act(async () => {
        render(
          <MemoryRouter>
            <MapPage />
          </MemoryRouter>
        )
      })
      expect(screen.getByTestId('mock-api-provider')).toBeInTheDocument()
    })

    it('shows search input', async () => {
      await act(async () => {
        render(
          <MemoryRouter>
            <MapPage />
          </MemoryRouter>
        )
      })
      expect(
        screen.getByPlaceholderText('Search pantries...')
      ).toBeInTheDocument()
    })
  })
})
