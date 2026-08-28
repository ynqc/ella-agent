import './App.css'
import { NavLink, Route, Routes } from 'react-router-dom'
import Chat from './pages/Chat'
import Home from './pages/Home'

function App() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="topbar-brand">Ella Agent</span>
        <nav className="topbar-nav" aria-label="Primary">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              isActive ? 'topbar-link topbar-link-active' : 'topbar-link'
            }
          >
            Home
          </NavLink>
          <NavLink
            to="/chat"
            className={({ isActive }) =>
              isActive ? 'topbar-link topbar-link-active' : 'topbar-link'
            }
          >
            Chat
          </NavLink>
        </nav>
      </header>

      <main className="content-shell">
        <div className="content-card">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/chat" element={<Chat />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

export default App
