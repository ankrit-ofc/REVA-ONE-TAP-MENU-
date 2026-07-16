interface Props {
  message?: string
  fullscreen?: boolean
}

export default function Loader({ message = 'Loading…', fullscreen = false }: Props) {
  const wrapper: React.CSSProperties = fullscreen
    ? {
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(255,255,255,0.8)',
        zIndex: 9999,
      }
    : { display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }

  return (
    <div role="status" aria-label={message} style={wrapper}>
      <span style={{ fontSize: '0.9375rem', color: '#6b7280' }}>{message}</span>
    </div>
  )
}
