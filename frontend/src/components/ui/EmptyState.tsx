interface EmptyStateProps {
  title: string
  description?: string
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
        color: 'var(--color-text-3)',
        textAlign: 'center',
        gap: 6,
      }}
    >
      <span style={{ fontSize: 13, color: 'var(--color-text-2)', fontWeight: 500 }}>{title}</span>
      {description && (
        <span style={{ fontSize: 12, maxWidth: 260, lineHeight: 1.6 }}>{description}</span>
      )}
    </div>
  )
}
