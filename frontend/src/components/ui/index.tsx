import { useEffect, useId, useRef, type ComponentProps, type ReactNode } from 'react'
import { TriangleAlert, X, type LucideIcon } from 'lucide-react'

export function Button({ variant = 'primary', className = '', type = 'button', ...props }: ComponentProps<'button'> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger' }) {
  return <button type={type} className={`button ${variant} ${className}`} {...props} />
}

export function Card({ className = '', ...props }: ComponentProps<'section'>) {
  return <section className={`card ${className}`} {...props} />
}

export function StatCard({ icon: Icon, label, value, detail, tone = 'brand' }: {
  icon: LucideIcon; label: string; value: ReactNode; detail?: string; tone?: string
}) {
  return <Card className="stat-card">
    <div className={`stat-icon tone-${tone}`}><Icon size={20} aria-hidden="true" /></div>
    <div className="stat-label">{label}</div>
    <strong>{value}</strong>
    {detail && <small>{detail}</small>}
  </Card>
}

export function Badge({ tone = 'neutral', children }: { tone?: string; children: ReactNode }) {
  return <span className={`pill tone-${tone}`}>{tone === 'warning' && <TriangleAlert size={14} aria-hidden="true" />}{children}</span>
}

export function Table({ label, children }: { label: string; children: ReactNode }) {
  return <div className="table-wrap" tabIndex={0} role="region" aria-label={label}><table>{children}</table></div>
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">
    <svg aria-hidden="true" width="64" height="56" viewBox="0 0 64 56" fill="none">
      <circle cx="32" cy="28" r="26" fill="var(--rose-200)" />
      <rect x="17" y="13" width="30" height="30" rx="6" fill="white" stroke="currentColor" strokeWidth="1.5" />
      <path d="M22 30h5l3-7 4 13 3-6h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
    <div>{children}</div>
  </div>
}

export function Skeleton({ label = 'Cargando…' }: { label?: string }) {
  return <div className="skeleton" role="status" aria-label={label}><span className="sr-only">{label}</span></div>
}

export function Modal({ title, children, onClose, busy = false, drawer = false }: {
  title: string; children: ReactNode; onClose: () => void; busy?: boolean; drawer?: boolean
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const id = useId()
  useEffect(() => {
    const element = dialog.current
    const previous = document.activeElement
    element?.showModal()
    return () => {
      element?.close()
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus()
    }
  }, [])
  return <dialog ref={dialog} aria-labelledby={id} className={drawer ? 'modal drawer' : 'modal'} onCancel={(event) => {
    event.preventDefault()
    if (!busy) onClose()
  }}>
    <header className="section-heading"><h2 id={id}>{title}</h2>
      <Button variant="ghost" aria-label="Cerrar" disabled={busy} onClick={onClose}><X size={20} aria-hidden="true" /></Button>
    </header>
    {children}
  </dialog>
}

export function Toast({ children }: { children: ReactNode }) {
  return <div className="toast" role="status">{children}</div>
}

export function Tabs({ label, options, value, onChange, children }: {
  label: string; options: { id: string; label: string }[]; value: string; onChange: (id: string) => void; children: ReactNode
}) {
  const id = useId()
  return <>
    <div className="tabs" role="tablist" aria-label={label}>{options.map((option, index) =>
      <button key={option.id} id={`${id}-${option.id}`} type="button" role="tab" aria-selected={value === option.id} aria-controls={`${id}-panel`} tabIndex={value === option.id ? 0 : -1}
        onClick={() => onChange(option.id)}
        onKeyDown={(event) => {
          const movement = { ArrowLeft: -1, ArrowRight: 1 }[event.key]
          if (movement === undefined && event.key !== 'Home' && event.key !== 'End') return
          event.preventDefault()
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : (index + (movement ?? 0) + options.length) % options.length
          onChange(options[next].id)
          event.currentTarget.parentElement?.querySelectorAll('button')[next]?.focus()
        }}>{option.label}</button>)}</div>
    <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${value}`} tabIndex={0}>{children}</div>
  </>
}
