import { lazy, Suspense, useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ChevronRight, ClipboardList, FolderOpen, History, Layers3, LayoutDashboard, LogOut, Menu, Scale, SunMoon, Users } from 'lucide-react'
import { useAuth } from './session'
import { ROLE } from './labels'
import { Brand, Disclaimer } from './components/Brand'
import { Button, Modal, Skeleton } from './components/ui'
import { api, type WorklistItem } from './api'
import { applyTheme, savedTheme, type Theme } from './theme'
import AccountPage from './pages/AccountPage'
import AuditPage from './pages/AuditPage'
import CaseDetailPage from './pages/CaseDetailPage'
import CasesPage from './pages/CasesPage'
import CohortDetailPage from './pages/CohortDetailPage'
import LoginPage from './pages/LoginPage'
import ModelsPage from './pages/ModelsPage'
import UsersPage from './pages/UsersPage'
import WorklistPage from './pages/WorklistPage'

const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const ComparePage = lazy(() => import('./pages/ComparePage'))
const AuditLogPage = lazy(() => import('./pages/AuditLogPage'))

export default function App() {
  const { user, loading, logout } = useAuth()
  const location = useLocation()
  const { pathname } = location
  const [menu, setMenu] = useState(false)
  const [theme, setTheme] = useState(savedTheme)
  const [worklist, setWorklist] = useState<{ userId: number; items: WorklistItem[] | null; error: string } | null>(null)
  const doctorId = user?.role === 'medico' ? user.id : undefined
  const pending = worklist?.userId === doctorId ? worklist : null

  useEffect(() => {
    const preference = window.matchMedia('(prefers-color-scheme: dark)')
    const sync = () => applyTheme(theme, preference.matches)
    sync()
    preference.addEventListener('change', sync)
    return () => preference.removeEventListener('change', sync)
  }, [theme])

  useEffect(() => {
    if (doctorId === undefined) return
    let alive = true
    let revision = 0
    const refresh = () => {
      const request = ++revision
      void api.worklist().then(items => {
        if (alive && request === revision) setWorklist({ userId: doctorId, items, error: '' })
      }).catch((err: Error) => {
        if (alive && request === revision) setWorklist({ userId: doctorId, items: null, error: err.message })
      })
    }
    refresh()
    const timer = window.setInterval(refresh, 30000)
    window.addEventListener('ecoaudit:reading-saved', refresh)
    return () => {
      alive = false
      window.clearInterval(timer)
      window.removeEventListener('ecoaudit:reading-saved', refresh)
    }
  }, [doctorId, location.key])

  if (loading) return <div className="app-loading"><Skeleton /></div>
  if (user === null) return <LoginPage />

  const admin = user.role === 'admin'
  const canAudit = user.role !== 'medico'
  const links = [
    { to: '/panel', label: 'Panel', icon: LayoutDashboard, visible: true },
    { to: '/casos', label: 'Casos', icon: FolderOpen, visible: true },
    { to: '/pendientes', label: 'Pendientes', icon: ClipboardList, visible: doctorId !== undefined },
    { to: '/auditoria', label: 'Auditoría', icon: ClipboardList, visible: canAudit },
    { to: '/comparar', label: 'Comparar modelos', icon: Scale, visible: canAudit },
    { to: '/modelos', label: 'Modelos', icon: Layers3, visible: true },
    { to: '/usuarios', label: 'Usuarios', icon: Users, visible: admin },
    { to: '/bitacora', label: 'Bitácora', icon: History, visible: admin },
  ].filter(item => item.visible)
  const section = links.find(item => pathname === item.to || pathname.startsWith(item.to + '/'))
  const inDetail = section && pathname !== section.to
  const initials = user.full_name.trim().split(/\s+/).slice(0, 2).map(part => part.charAt(0)).join('').toUpperCase()

  function sidebar() {
    return <>
      <Link className="brand-link" to="/panel" onClick={() => setMenu(false)}><Brand /></Link>
      <nav aria-label="Navegación principal" className="main-nav">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} onClick={() => setMenu(false)}>
            <Icon size={19} aria-hidden="true" /><span>{label}</span>
            {to === '/pendientes' && pending?.items && <span className="count">{pending.items.length}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="session">
        <span className="avatar" aria-hidden="true">{initials}</span>
        <span className="session-identity">
          <Link to="/cuenta" title="Mi cuenta" onClick={() => setMenu(false)}>{user?.full_name}</Link>
          <span>{' · '}{user && ROLE[user.role]}</span>
        </span>
        <Button variant="ghost" className="logout" onClick={() => { setMenu(false); logout() }}><LogOut size={16} aria-hidden="true" /> Salir</Button>
      </div>
    </>
  }

  return <div className="shell">
    <a className="skip-link" href="#contenido">Saltar al contenido</a>
    <aside className="sidebar">{sidebar()}</aside>
    {menu && <Modal title="Menú" drawer onClose={() => setMenu(false)}><div className="mobile-nav">{sidebar()}</div></Modal>}
    <div className="shell-content">
      <header className="topbar">
        <Button variant="ghost" className="menu-toggle" onClick={() => setMenu(true)} aria-haspopup="dialog"><Menu size={21} aria-hidden="true" /> Menú</Button>
        <div className="breadcrumbs">
          <Link to="/panel">EcoAudit</Link><ChevronRight size={15} aria-hidden="true" />
          {inDetail ? <><Link to={section.to}>{section.label}</Link><ChevronRight size={15} aria-hidden="true" /><strong>Detalle</strong></>
            : <strong>{section?.label ?? (pathname === '/cuenta' ? 'Mi cuenta' : 'Panel')}</strong>}
        </div>
        <label className="theme-picker">
          <SunMoon size={19} aria-hidden="true" />
          <span className="sr-only">Apariencia</span>
          <select value={theme} onChange={event => {
            const next = event.target.value as Theme
            setTheme(next)
            try { localStorage.setItem('ecoaudit.theme', next) } catch {
              // La preferencia se conserva durante esta visita.
            }
          }}><option value="claro">Claro</option><option value="oscuro">Oscuro</option><option value="sistema">Sistema</option></select>
        </label>
      </header>
      <main id="contenido" tabIndex={-1}>
        <Suspense fallback={<Skeleton />}>
          <Routes>
            <Route path="/panel" element={<DashboardPage />} />
            <Route path="/casos" element={<CasesPage />} />
            <Route path="/casos/:caseId" element={<CaseDetailRoute />} />
            {doctorId !== undefined && <Route path="/pendientes" element={<WorklistPage items={pending?.items ?? null} error={pending?.error ?? ''} />} />}
            {canAudit && <Route path="/auditoria" element={<AuditPage />} />}
            {canAudit && <Route path="/auditoria/:cohortId" element={<CohortDetailRoute />} />}
            {canAudit && <Route path="/comparar" element={<ComparePage />} />}
            <Route path="/modelos" element={<ModelsPage />} />
            <Route path="/cuenta" element={<AccountPage />} />
            {admin && <Route path="/usuarios" element={<UsersPage />} />}
            {admin && <Route path="/bitacora" element={<AuditLogPage />} />}
            <Route path="*" element={<Navigate to={user.role === 'investigador' ? '/auditoria' : '/panel'} replace />} />
          </Routes>
        </Suspense>
      </main>
      <Disclaimer />
    </div>
  </div>
}

function CaseDetailRoute() {
  const { pathname, search } = useLocation()
  return <CaseDetailPage key={pathname + search} />
}

function CohortDetailRoute() {
  return <CohortDetailPage key={useLocation().pathname} />
}
