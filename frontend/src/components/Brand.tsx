export function Brand() {
  return <div className="brand">
    <svg viewBox="0 0 48 48" aria-hidden="true" fill="none">
      <rect width="48" height="48" rx="14" fill="white" fillOpacity=".16" />
      <path d="M12 37c5-5 12-14 16-22 2-4-1-7-4-7s-6 3-4 7c4 8 10 17 16 22" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 25h8l3-4 5 9 5-10 4 5h9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
    <span>EcoAudit</span>
  </div>
}

export function Disclaimer() {
  return <footer className="disclaimer">
    <strong>Prototipo de investigación.</strong> No es un dispositivo médico ni reemplaza el criterio profesional; no debe usarse para decidir la atención de un paciente.
  </footer>
}
