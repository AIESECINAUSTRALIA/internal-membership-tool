import { useEffect, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

function App() {
  const [apiStatus, setApiStatus] = useState('checking…')

  useEffect(() => {
    fetch(`${API_URL}/healthz`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: { status: string }) => setApiStatus(data.status))
      .catch(() => setApiStatus('unreachable'))
  }, [])

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '4rem 1.5rem', textAlign: 'center' }}>
      <h1>Hello World</h1>
      <p>AIESEC Australia — Membership Tool</p>
      <p style={{ color: '#6b6375' }}>
        API health: <strong>{apiStatus}</strong>
      </p>
    </main>
  )
}

export default App
