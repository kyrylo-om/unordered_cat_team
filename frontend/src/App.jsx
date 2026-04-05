import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const [message, setMessage] = useState('Loading...')
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadMessage() {
      try {
        const response = await fetch('/api/hello/')
        if (!response.ok) {
          throw new Error('Request failed')
        }

        const data = await response.json()
        setMessage(data.message)
      } catch {
        setError('Could not reach Django backend')
      }
    }

    loadMessage()
  }, [])

  return (
    <main className="app">
      <h1>Django + React</h1>
      <p>{error || message}</p>
    </main>
  )
}

export default App
