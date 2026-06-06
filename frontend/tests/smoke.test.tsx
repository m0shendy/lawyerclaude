import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

function Hello({ name }: { name: string }) {
  return <p dir="rtl">مرحباً {name}</p>
}

describe('test harness smoke test', () => {
  it('renders a component into jsdom', () => {
    render(<Hello name="مكتب المحاماة" />)
    expect(screen.getByText('مرحباً مكتب المحاماة')).toBeInTheDocument()
  })
})
