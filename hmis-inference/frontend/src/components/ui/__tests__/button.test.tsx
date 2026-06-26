import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Button } from '../button'

describe('Button', () => {
  it('renders its children', () => {
    render(<Button>Press me</Button>)
    expect(screen.getByRole('button', { name: /press me/i })).toBeInTheDocument()
  })

  it('forwards additional class names', () => {
    render(<Button className="extra-class">OK</Button>)
    expect(screen.getByRole('button')).toHaveClass('extra-class')
  })

  it('renders as a slot when asChild is true', () => {
    render(
      <Button asChild>
        <a href="/somewhere">Link as button</a>
     </Button>,
    )
    // The underlying element becomes the <a>, not the <button>.
    const link = screen.getByRole('link', { name: /link as button/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/somewhere')
  })

  it('respects disabled state', () => {
    render(<Button disabled>Off</Button>)
    expect(screen.getByRole('button', { name: /off/i })).toBeDisabled()
  })
})
