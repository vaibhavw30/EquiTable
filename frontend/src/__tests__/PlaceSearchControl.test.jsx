import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Track the Autocomplete instance created by PlaceSearchControl
let mockAutocompleteInstance
let mockAddListener

vi.mock('@vis.gl/react-google-maps', () => ({
  MapControl: ({ children }) => <div data-testid="mock-map-control">{children}</div>,
  ControlPosition: { TOP: 'TOP' },
  useMapsLibrary: (lib) => {
    if (lib === 'places') {
      return {
        Autocomplete: vi.fn(function (input, opts) {
          this.input = input
          this.opts = opts
          this.listeners = {}
          this.addListener = vi.fn((event, cb) => {
            this.listeners[event] = cb
          })
          this.getPlace = vi.fn()
          mockAutocompleteInstance = this
          mockAddListener = this.addListener
        }),
      }
    }
    return null
  },
}))

import PlaceSearchControl from '../components/PlaceSearchControl'

describe('PlaceSearchControl', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAutocompleteInstance = null
    mockAddListener = null
  })

  it('renders search input', () => {
    render(<PlaceSearchControl onPlaceSelect={() => {}} />)
    expect(screen.getByTestId('place-search-input')).toBeInTheDocument()
  })

  it('renders inside MapControl', () => {
    render(<PlaceSearchControl onPlaceSelect={() => {}} />)
    expect(screen.getByTestId('mock-map-control')).toBeInTheDocument()
  })

  it('renders with correct placeholder', () => {
    render(<PlaceSearchControl onPlaceSelect={() => {}} />)
    expect(screen.getByPlaceholderText('Search for a location...')).toBeInTheDocument()
  })

  it('creates Autocomplete when places library loads', () => {
    render(<PlaceSearchControl onPlaceSelect={() => {}} />)
    expect(mockAutocompleteInstance).not.toBeNull()
    expect(mockAddListener).toHaveBeenCalledWith('place_changed', expect.any(Function))
  })

  it('calls onPlaceSelect when a place is selected', () => {
    const onPlaceSelect = vi.fn()
    render(<PlaceSearchControl onPlaceSelect={onPlaceSelect} />)

    // Simulate place selection
    mockAutocompleteInstance.getPlace.mockReturnValue({
      geometry: {
        location: {
          lat: () => 40.7128,
          lng: () => -74.006,
        },
      },
      name: 'New York City',
    })

    // Trigger the place_changed listener
    mockAutocompleteInstance.listeners['place_changed']()

    expect(onPlaceSelect).toHaveBeenCalledWith({
      lat: 40.7128,
      lng: -74.006,
      name: 'New York City',
    })
  })

  it('does not call onPlaceSelect if place has no geometry', () => {
    const onPlaceSelect = vi.fn()
    render(<PlaceSearchControl onPlaceSelect={onPlaceSelect} />)

    mockAutocompleteInstance.getPlace.mockReturnValue({})
    mockAutocompleteInstance.listeners['place_changed']()

    expect(onPlaceSelect).not.toHaveBeenCalled()
  })
})
