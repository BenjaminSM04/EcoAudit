import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './session'
import { ROLE } from './labels'
import CaseDetailPage from './pages/CaseDetailPage'
import AuditPage from './pages/AuditPage'
import CasesPage from './pages/CasesPage'
import LoginPage from './pages/LoginPage'
import ModelsPage from './pages/ModelsPage'
import UsersPage from './pages/UsersPage'

export default function App() {
  const { user, loading, logout } = useAuth()

  if (loading) return <p className="center-note">Cargando…</p>
  if (user === null) return <LoginPage />

  const clinical = user.role === 'medico' || user.role === 'admin'
  const home = clinical ? '/casos' : '/auditoria'

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">EcoAudit</span>
        <nav>
          {clinical && <NavLink to="/casos">Casos</NavLink>}
          {user.role !== 'medico' && <NavLink to="/auditoria">Auditoría</NavLink>}
          <NavLink to="/modelos">Modelos</NavLink>
          {user.role === 'admin' && <NavLink to="/usuarios">Usuarios</NavLink>}
        </nav>
        <div className="session">
          <span>
            {user.full_name} · {ROLE[user.role]}
          </span>
          <button className="link" onClick={logout}>
            Salir
          </button>
        </div>
      </header>

      <main>
        <Routes>
          {clinical && <Route path="/casos" element={<CasesPage />} />}
          {clinical && <Route path="/casos/:caseId" element={<CaseDetailPage />} />}
          {user.role !== 'medico' && <Route path="/auditoria" element={<AuditPage />} />}
          <Route path="/modelos" element={<ModelsPage />} />
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
