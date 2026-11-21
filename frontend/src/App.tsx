import { lazy, Suspense, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ChevronRight, ClipboardList, FolderOpen, History, Layers3, LayoutDashboard, LogOut, Menu, Scale, Users } from 'lucide-react'
import { useAuth } from './session'
import { ROLE } from './labels'
import { Brand, Disclaimer } from './components/Brand'
import { Button, Modal, Skeleton } from './components/ui'
import AccountPage from './pages/AccountPage'
import AuditPage from './pages/AuditPage'
import CaseDetailPage from './pages/CaseDetailPage'
import CasesPage from './pages/CasesPage'
import CohortDetailPage from './pages/CohortDetailPage'
import LoginPage from './pages/LoginPage'
import ModelsPage from './pages/ModelsPage'
import UsersPage from './pages/UsersPage'

const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const ComparePage = lazy(() => import('./pages/ComparePage'))
const AuditLogPage = lazy(() => import('./pages/AuditLogPage'))

export default function App() {
  const { user, loading, logout } = useAuth()
  const { pathname } = useLocation()
  const [menu, setMenu] = useState(false)

  if (loading) return <div className="app-loading"><Skeleton /></div>
  if (user === null) return <LoginPage />

  const admin = user.role === 'admin'
  const canAudit = user.role !== 'medico'
  const links = [
    { to: '/panel', label: 'Panel', icon: LayoutDashboard, visible: true },
    { to: '/casos', label: 'Casos', icon: FolderOpen, visible: true },
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
      </header>
      <main id="contenido" tabIndex={-1}>
        <Suspense fallback={<Skeleton />}>
          <Routes>
            <Route path="/panel" element={<DashboardPage />} />
            <Route path="/casos" element={<CasesPage />} />
            <Route path="/casos/:caseId" element={<CaseDetailRoute />} />
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
  return <CaseDetailPage key={useLocation().pathname} />
}

function CohortDetailRoute() {
  return <CohortDetailPage key={useLocation().pathname} />
}
