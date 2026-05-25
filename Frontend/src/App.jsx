import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001'

function App() {
  const [summary, setSummary] = useState({ total_in: 0, total_out: 0, current_inside: 0, events: 0 })
  const [events, setEvents] = useState([])
  const [status, setStatus] = useState('Conectando')
  const [isSaving, setIsSaving] = useState(false)

  const lastEvent = useMemo(() => events[0], [events])

  async function loadData() {
    try {
      const [summaryResponse, eventsResponse] = await Promise.all([
        fetch(`${API_URL}/counts/summary`),
        fetch(`${API_URL}/counts/events?limit=8`),
      ])

      if (!summaryResponse.ok || !eventsResponse.ok) {
        throw new Error('API unavailable')
      }

      setSummary(await summaryResponse.json())
      setEvents(await eventsResponse.json())
      setStatus('En linea')
    } catch {
      setStatus('Sin conexion')
    }
  }

  async function registerEvent(direction) {
    setIsSaving(true)
    try {
      await fetch(`${API_URL}/counts/events`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cameraId: 'camara_prueba',
          direction,
          quantity: 1,
          metadata: { source: 'dashboard-test' },
        }),
      })
      await loadData()
    } finally {
      setIsSaving(false)
    }
  }

  useEffect(() => {
    loadData()
    const interval = window.setInterval(loadData, 5000)
    return () => window.clearInterval(interval)
  }, [])

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Sistema de conteo</p>
          <h1>Monitoreo de personas</h1>
        </div>
        <div className={`status ${status === 'En linea' ? 'online' : 'offline'}`}>
          {status}
        </div>
      </header>

      <section className="metrics" aria-label="Resumen de conteo">
        <article>
          <span>Ingresos</span>
          <strong>{summary.total_in}</strong>
        </article>
        <article>
          <span>Salidas</span>
          <strong>{summary.total_out}</strong>
        </article>
        <article>
          <span>Dentro ahora</span>
          <strong>{summary.current_inside}</strong>
        </article>
        <article>
          <span>Eventos</span>
          <strong>{summary.events}</strong>
        </article>
      </section>

      <section className="workspace">
        <div className="panel video-panel">
          <div className="camera-frame">
            <div className="scan-line" />
            <div className="camera-copy">
              <span>Camara IP</span>
              <strong>Esperando stream RTSP</strong>
            </div>
          </div>
          <div className="actions">
            <button type="button" onClick={() => registerEvent('in')} disabled={isSaving}>
              Registrar ingreso
            </button>
            <button type="button" onClick={() => registerEvent('out')} disabled={isSaving}>
              Registrar salida
            </button>
          </div>
        </div>

        <div className="panel activity-panel">
          <div className="panel-heading">
            <h2>Actividad reciente</h2>
            {lastEvent ? <span>Ultimo ID {lastEvent.id}</span> : <span>Sin eventos</span>}
          </div>
          <div className="event-list">
            {events.length === 0 ? (
              <p className="empty-state">Aun no hay eventos registrados.</p>
            ) : (
              events.map((event) => (
                <div className="event-row" key={event.id}>
                  <div>
                    <strong>{event.direction === 'in' ? 'Ingreso' : 'Salida'}</strong>
                    <span>{event.camera_id}</span>
                  </div>
                  <time>{new Date(event.occurred_at).toLocaleString()}</time>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </main>
  )
}

export default App
