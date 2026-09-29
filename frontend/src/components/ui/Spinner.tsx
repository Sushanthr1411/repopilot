interface SpinnerProps {
  size?: number
  className?: string
}

export function Spinner({ size = 16, className = '' }: SpinnerProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      className={className}
      style={{ animation: 'spin 0.8s linear infinite' }}
      aria-label="Loading"
    >
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2" />
      <path
        d="M14 8a6 6 0 0 0-6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}
