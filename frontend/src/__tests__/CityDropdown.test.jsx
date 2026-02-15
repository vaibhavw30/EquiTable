import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CityDropdown from '../components/CityDropdown'

const mockCities = [
  { city: 'Atlanta', state: 'GA', count: 15, center: { lat: 33.749, lng: -84.388 } },
  { city: 'New York City', state: 'NY', count: 5, center: { lat: 40.7128, lng: -74.006 } },
]

describe('CityDropdown', () => {
  it('shows "All Cities" when no city selected', () => {
    render(
      <CityDropdown cities={mockCities} selectedCity={null} onSelect={vi.fn()} loading={false} />
    )
    expect(screen.getByText('All Cities')).toBeInTheDocument()
  })

  it('shows selected city name', () => {
    render(
      <CityDropdown
        cities={mockCities}
        selectedCity={{ city: 'Atlanta', state: 'GA' }}
        onSelect={vi.fn()}
        loading={false}
      />
    )
    expect(screen.getByText('Atlanta, GA')).toBeInTheDocument()
  })

  it('opens dropdown and shows city list on click', () => {
    render(
      <CityDropdown cities={mockCities} selectedCity={null} onSelect={vi.fn()} loading={false} />
    )
    // Click the dropdown button
    fireEvent.click(screen.getByText('All Cities'))
    // Should show city options
    expect(screen.getByText('Atlanta, GA')).toBeInTheDocument()
    expect(screen.getByText('New York City, NY')).toBeInTheDocument()
  })

  it('calls onSelect with city when option clicked', () => {
    const onSelect = vi.fn()
    render(
      <CityDropdown cities={mockCities} selectedCity={null} onSelect={onSelect} loading={false} />
    )
    fireEvent.click(screen.getByText('All Cities'))
    fireEvent.click(screen.getByText('Atlanta, GA'))
    expect(onSelect).toHaveBeenCalledWith(mockCities[0])
  })

  it('calls onSelect with null when "All Cities" clicked', () => {
    const onSelect = vi.fn()
    render(
      <CityDropdown
        cities={mockCities}
        selectedCity={{ city: 'Atlanta', state: 'GA' }}
        onSelect={onSelect}
        loading={false}
      />
    )
    // Open dropdown (click the button showing "Atlanta, GA")
    fireEvent.click(screen.getByRole('button'))
    // Click "All Cities" option
    fireEvent.click(screen.getAllByText('All Cities')[0])
    expect(onSelect).toHaveBeenCalledWith(null)
  })

  it('shows pantry counts', () => {
    render(
      <CityDropdown cities={mockCities} selectedCity={null} onSelect={vi.fn()} loading={false} />
    )
    fireEvent.click(screen.getByText('All Cities'))
    expect(screen.getByText('15')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })
})
