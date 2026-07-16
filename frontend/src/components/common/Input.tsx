import type { InputHTMLAttributes } from 'react'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
}

export default function Input({ label, error, id, ...rest }: Props) {
  const inputId = id ?? label.toLowerCase().replace(/\s+/g, '-')

  return (
    <div style={{ marginBottom: '1rem' }}>
      <label
        htmlFor={inputId}
        style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.25rem' }}
      >
        {label}
      </label>
      <input
        id={inputId}
        style={{
          display: 'block',
          width: '100%',
          padding: '0.5rem 0.75rem',
          border: error ? '1px solid #dc2626' : '1px solid #d1d5db',
          borderRadius: '0.375rem',
          fontSize: '0.9375rem',
          outline: 'none',
          boxSizing: 'border-box',
        }}
        {...rest}
      />
      {error && (
        <span
          role="alert"
          style={{ fontSize: '0.8125rem', color: '#dc2626', marginTop: '0.25rem', display: 'block' }}
        >
          {error}
        </span>
      )}
    </div>
  )
}
