import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CitySelector from '../components/CitySelector'

const mockCities = [
  { city: 'Atlanta', state: 'GA', count: 15, center: { lat: 33.749, lng: -84.388 } },
  { city: 'New York City', state: 'NY', count: 5, center: { lat: 40.7128, lng: -74.006 } },
  { city: 'Chicago', state: 'IL', count: 5, center: { lat: 41.8781, lng: -87.6298 } },
]

describe('CitySelector', () => {
  it('renders city cards', () => {
    render(
      <CitySelector cities={mockCities} loading={false} onSelect={vi.fn()} />
    )
    expect(screen.getByText('Atlanta')).toBeInTheDocument()
    expect(screen.getByText('New York City')).toBeInTheDocument()
    expect(screen.getByText('Chicago')).toBeInTheDocument()
  })

  it('shows pantry counts', () => {
    render(
      <CitySelector cities={mockCities} loading={false} onSelect={vi.fn()} />
    )
    expect(screen.getByText(/15 pantries/)).toBeInTheDocument()
    expect(screen.getAllByText(/5 pantries/).length).toBeGreaterThanOrEqual(2)
  })

  it('calls onSelect when a city is clicked', () => {
    const onSelect = vi.fn()
    render(
      <CitySelector cities={mockCities} loading={false} onSelect={onSelect} />
    )
    fireEvent.click(screen.getByText('Atlanta'))
    expect(onSelect).toHaveBeenCalledWith(mockCities[0])
  })

  it('shows loading spinner', () => {
    render(
      <CitySelector cities={[]} loading={true} onSelect={vi.fn()} />
    )
    expect(screen.queryByText('Atlanta')).not.toBeInTheDocument()
  })

  it('shows close button when onClose is provided', () => {
    const onClose = vi.fn()
    render(
      <CitySelector cities={mockCities} loading={false} onSelect={vi.fn()} onClose={onClose} />
    )
    // The X button should be present
    const buttons = screen.getAllByRole('button')
    // First button is the close button (X icon)
    fireEvent.click(buttons[0])
    expect(onClose).toHaveBeenCalled()
  })

  it('shows empty state', () => {
    render(
      <CitySelector cities={[]} loading={false} onSelect={vi.fn()} />
    )
    expect(screen.getByText('No cities available')).toBeInTheDocument()
  })
})
