import type { Track } from '../types/music'

async function getTracks(endpoint: string): Promise<Track[]> {
  const response = await fetch(endpoint, {
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
    },
  })

  if (response.status === 401 || response.status === 403) {
    throw new Error('Necesitas iniciar sesión en OSTOR.')
  }

  if (!response.ok) {
    throw new Error(`Error del servidor: ${response.status}`)
  }

  const contentType = response.headers.get('content-type') || ''

  if (!contentType.includes('application/json')) {
    throw new Error(
      'El servidor no devolvió datos musicales. Comprueba el inicio de sesión.'
    )
  }

  const data: unknown = await response.json()

  if (!Array.isArray(data)) {
    throw new Error('Formato de respuesta musical no válido.')
  }

  return data as Track[]
}

export function searchTracks(query: string, page = 1): Promise<Track[]> {
  const text = query.trim()

  if (!text) {
    return Promise.resolve([])
  }

  return getTracks(`/api/search?q=${encodeURIComponent(text)}&page=${page}`)
}

export function getTrendingTracks(): Promise<Track[]> {
  return getTracks('/api/trending')
}

