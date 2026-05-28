import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001'
const VISION_URL = import.meta.env.VITE_VISION_URL || 'http://localhost:5001'

function App() {
  const [summary, setSummary] = useState({ total_in: 0, total_out: 0, current_inside: 0, events: 0 })
  const [events, setEvents] = useState([])
  const [vision, setVision] = useState({ connected: false, detections: 0, tracks: 0, cameraId: 'garaje' })
  const [status, setStatus] = useState('Conectando')
  const [isSaving, setIsSaving] = useState(false)

  const lastEvent = useMemo(() => events[0], [events])
  const liveDetections = vision.detections ?? 0
  const occupancyLabel = liveDetections > 0 ? 'Con movimiento' : 'Disponible'

  async function loadData() {
    let backendOnline = false
    let visionOnline = false

    try {
      const summaryResponse = await fetch(`${API_URL}/counts/summary`)
      if (summaryResponse.ok) {
        setSummary(await summaryResponse.json())
        backendOnline = true
      }
    } catch {
      backendOnline = false
    }

    try {
      const eventsResponse = await fetch(`${API_URL}/counts/events?limit=8`)
      if (eventsResponse.ok) {
        setEvents(await eventsResponse.json())
        backendOnline = true
      }
    } catch {
      backendOnline = false
    }

    try {
      const visionResponse = await fetch(`${VISION_URL}/status`)
      if (visionResponse.ok) {
        const visionData = await visionResponse.json()
        setVision(visionData)
        visionOnline = Boolean(visionData.connected)
      }
    } catch {
      visionOnline = false
    }

    if (visionOnline && backendOnline) {
      setStatus('En linea')
    } else if (visionOnline) {
      setStatus('Vision activa')
    } else {
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
          cameraId: vision.cameraId || 'garaje',
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
    const interval = window.setInterval(loadData, 1000)
    return () => window.clearInterval(interval)
  }, [])

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Sistema de conteo por vision artificial</p>
          <h1>Monitoreo de aforo en tiempo real</h1>
        </div>
        <div className={`status ${status === 'En linea' ? 'online' : 'offline'}`}>
          {status}
        </div>
      </header>

      <section className="metrics" aria-label="Resumen de conteo">
        <article>
          <span>Personas detectadas</span>
          <strong>{liveDetections}</strong>
        </article>
        <article>
          <span>Ingresos</span>
          <strong>{summary.total_in}</strong>
        </article>
        <article>
          <span>Salidas</span>
          <strong>{summary.total_out}</strong>
        </article>
        <article>
          <span>Estado sala</span>
          <strong className="label-metric">{occupancyLabel}</strong>
        </article>
      </section>

      <section className="workspace">
        <div className="panel video-panel">
          <div className="panel-heading">
            <div>
              <h2>Camara {vision.cameraId || 'garaje'}</h2>
              <span>{vision.connected ? 'Video procesado por Vision' : 'Esperando video'}</span>
            </div>
            <span className={`live-pill ${vision.connected ? 'active' : ''}`}>LIVE</span>
          </div>
          <div className="camera-frame">
            <img src={`${VISION_URL}/video.mjpg`} alt="Video procesado con detecciones" />
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
            <div>
              <h2>Actividad reciente</h2>
              <span>{lastEvent ? `Ultimo evento ID ${lastEvent.id}` : 'Sin eventos registrados'}</span>
            </div>
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
