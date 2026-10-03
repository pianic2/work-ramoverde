import { Link, Navigate, Route, Routes } from 'react-router-dom';
import { PasswordResetConfirm, PasswordResetRequest } from '../auth/PasswordPages';
import { StaffHome } from '../auth/StaffHome';
import { StaffLogin } from '../auth/StaffLogin';

function Home() {
  return (
    <main className="shell">
      <header>
        <strong>RamoVerde</strong>
        <nav>
          <Link to="/admin">Area riservata</Link>
        </nav>
      </header>
      <section className="hero">
        <h1>RamoVerde</h1>
        <p className="lede">Il nuovo sito di RAMO VERDE SRL è in preparazione.</p>
      </section>
    </main>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/admin/login" element={<StaffLogin />} />
      <Route path="/admin/password-reset" element={<PasswordResetRequest />} />
      <Route path="/admin/reset-password" element={<PasswordResetConfirm />} />
      <Route path="/admin" element={<StaffHome />} />
      <Route path="/account" element={<Navigate to="/admin" replace />} />
      <Route
        path="*"
        element={
          <main className="shell">
            <h1>Pagina non trovata</h1>
            <Link to="/">Torna alla home</Link>
          </main>
        }
      />
    </Routes>
  );
}
