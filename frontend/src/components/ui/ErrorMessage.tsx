import { AlertTriangle } from 'lucide-react'

interface ErrorMessageProps {
  message: string
  compact?: boolean
}

export function ErrorMessage({ message, compact }: ErrorMessageProps) {
  if (compact) {
    return (
      <span style={{ color: 'var(--color-error)', fontSize: 12 }}>
        {message}
      </span>
    )
  }
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        padding: '10px 14px',
        background: 'color-mix(in srgb, var(--color-error) 8%, transparent)',
        border: '1px solid color-mix(in srgb, var(--color-error) 25%, transparent)',
        borderRadius: 'var(--radius)',
        color: 'var(--color-error)',
        fontSize: 12,
      }}
    >
      <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
      <span>{message}</span>
    </div>
  )
}
