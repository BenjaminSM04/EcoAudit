import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './session'
import { ROLE } from './labels'
import AccountPage from './pages/AccountPage'
import AuditPage from './pages/AuditPage'
import CaseDetailPage from './pages/CaseDetailPage'
import CasesPage from './pages/CasesPage'
import CohortDetailPage from './pages/CohortDetailPage'
import LoginPage from './pages/LoginPage'
import ModelsPage from './pages/ModelsPage'
import UsersPage from './pages/UsersPage'

export default function App() {
  const { user, loading, logout } = useAuth()

  if (loading) return <p className="center-note">Cargando…</p>
  if (user === null) return <LoginPage />

  // Casos: todos los roles (el backend limita a los propios, salvo admin).
  // Auditoría de cohortes: investigador y admin. Usuarios: solo admin.
  const canAudit = user.role === 'investigador' || user.role === 'admin'
  const home = user.role === 'investigador' ? '/auditoria' : '/casos'

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">EcoAudit</span>
        <nav>
          <NavLink to="/casos">Casos</NavLink>
          {canAudit && <NavLink to="/auditoria">Auditoría</NavLink>}
          <NavLink to="/modelos">Modelos</NavLink>
          {user.role === 'admin' && <NavLink to="/usuarios">Usuarios</NavLink>}
        </nav>
        <div className="session">
          <span>
            <Link to="/cuenta" title="Mi cuenta">
              {user.full_name}
            </Link>{' '}
            · {ROLE[user.role]}
          </span>
          <button className="link" onClick={() => logout()}>
            Salir
          </button>
        </div>
      </header>

      <main>
        <Routes>
          <Route path="/casos" element={<CasesPage />} />
          <Route path="/casos/:caseId" element={<CaseDetailPage />} />
          {canAudit && <Route path="/auditoria" element={<AuditPage />} />}
          {canAudit && <Route path="/auditoria/:cohortId" element={<CohortDetailPage />} />}
          <Route path="/modelos" element={<ModelsPage />} />
          <Route path="/cuenta" element={<AccountPage />} />
          {user.role === 'admin' && <Route path="/usuarios" element={<UsersPage />} />}
          <Route path="*" element={<Navigate to={home} replace />} />
        </Routes>
      </main>

      <footer className="disclaimer">
        Prototipo de investigación. No es un dispositivo médico ni reemplaza el criterio
        profesional; no debe usarse para decidir la atención de un paciente.
      </footer>
    </div>
  )
}
