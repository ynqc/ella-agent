import './App.css'
import { NavLink, Route, Routes } from 'react-router-dom'
import Chat from './pages/Chat'
import Home from './pages/Home'

function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="eyebrow">Ella Agent</p>
          <h1>Workspace</h1>
          <p className="brand-copy">
            Manage navigation on the left and render each route in a dedicated
            workspace on the right.
          </p>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              isActive ? 'nav-link nav-link-active' : 'nav-link'
            }
          >
            Home
          </NavLink>
          <NavLink
            to="/chat"
            className={({ isActive }) =>
              isActive ? 'nav-link nav-link-active' : 'nav-link'
            }
          >
            Chat
          </NavLink>
        </nav>
      </aside>

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
