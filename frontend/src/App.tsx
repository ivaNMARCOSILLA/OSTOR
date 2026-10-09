import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { MusicSource, Track } from './types/music'
import { getTrendingTracks, searchTracks } from './services/musicApi'
import './App.css'

type Filter = MusicSource | 'TODAS'

const filters: Filter[] = [
  'TODAS', 'ARCHIVE', 'AUDIUS', 'JAMENDO'
]

export default function App() {
  const [query, setQuery] = useState('')
  const [activeQuery, setActiveQuery] = useState('')
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const requestId = useRef(0)
  const [tracks, setTracks] = useState<Track[]>([])
  const [currentTrack, setCurrentTrack] = useState<Track | null>(null)
  const [playing, setPlaying] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [filter, setFilter] = useState<Filter>('TODAS')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('Preparando el universo musical...')

  useEffect(() => {
    let active = true

    getTrendingTracks()
      .then(data => {
        if (!active) return
        setTracks(data.filter(track => ['ARCHIVE', 'AUDIUS', 'JAMENDO'].includes(track.source)))
        setMessage(data.length
          ? `${data.length} canciones para descubrir`
          : 'No hay resultados disponibles.')
      })
      .catch(error => {
        if (active) setMessage(String(error))
      })

    return () => { active = false }
  }, [])

  async function runSearch(text: string) {
    const search = text.trim()
    if (!search) return

    const id = ++requestId.current
    setActiveQuery(search)
    setPage(1)
    setHasMore(false)
    setLoading(true)
    setMessage('Buscando nuevas frecuencias...')

    try {
      const data = await searchTracks(search, 1)
      if (id !== requestId.current) return

      setTracks(data.filter(track => ['ARCHIVE', 'AUDIUS', 'JAMENDO'].includes(track.source)))
      setFilter('TODAS')
      setHasMore(data.length > 0)
      setMessage(`${data.length} resultados encontrados`)
    } catch (error) {
      if (id !== requestId.current) return
      setMessage(error instanceof Error ? error.message : 'Error de busqueda')
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  async function loadMoreTracks() {
    if (!activeQuery || loading || !hasMore) return

    const id = requestId.current
    const nextPage = page + 1
    setLoading(true)
    setMessage(`Cargando pagina ${nextPage}...`)

    try {
      const data = await searchTracks(activeQuery, nextPage)
      if (id !== requestId.current) return

      setTracks(previous => {
        const seen = new Set(previous.map(track => track.id))
        const additional = data.filter(track => {
          if (!['ARCHIVE', 'AUDIUS', 'JAMENDO'].includes(track.source)) return false
          if (seen.has(track.id)) return false
          seen.add(track.id)
          return true
        })
        return [...previous, ...additional]
      })

      setPage(nextPage)
      setHasMore(data.length > 0)
      setMessage(`${data.length} resultados recibidos de la pagina ${nextPage}`)
    } catch (error) {
      if (id !== requestId.current) return
      setMessage(error instanceof Error ? error.message : 'Error al cargar mas')
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!query.trim()) return

    await runSearch(query)
  }

  function playTrack(track: Track) {
    setCurrentTrack(track)
    setPlaying(true)
  }

  function nextTrack() {
    if (!currentTrack) return
    const index = tracks.findIndex(track => track.id === currentTrack.id)
    if (index < 0) return
    const next = tracks[(index + 1) % tracks.length]
    if (next) playTrack(next)
  }

  function previousTrack() {
    if (!currentTrack) return
    const index = tracks.findIndex(track => track.id === currentTrack.id)
    if (index < 0) return
    const previous = tracks[(index - 1 + tracks.length) % tracks.length]
    if (previous) playTrack(previous)
  }

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !currentTrack) return

    if (playing) {
      void audio.play().catch(() => {
        setPlaying(false)
        setMessage('El navegador no pudo iniciar el audio. Pulsa PLAY de nuevo.')
      })
    } else {
      audio.pause()
    }
  }, [currentTrack, playing])

  function togglePlayback() {
    if (!currentTrack) return

    const audio = audioRef.current

    if (!audio) {
      setPlaying(value => !value)
      return
    }

    if (audio.paused) {
      void audio.play().catch(() => {
        setPlaying(false)
        setMessage('No se pudo iniciar la reproduccion de esta pista.')
      })
    } else {
      audio.pause()
    }
  }
  const visible = tracks.filter(
    track => filter === 'TODAS' || track.source === filter
  )

  return (
    <div className="ostor">
      <aside className="sidebar">
        <div className="brand">OSTOR<span>✦</span></div>
        <div className="side-caption">YOUR SOUND. YOUR UNIVERSE.</div>

        <nav className="navigation">
          <a className="nav-active" href="#inicio">◈ &nbsp; Descubrir</a>
          <a href="#catalogo">▦ &nbsp; Explorar catálogo</a>
        </nav>

        <div className="side-footer">
          <span className="signal" /> NEXUS ENGINE
          <small>REACT / TYPESCRIPT</small>
        </div>
      </aside>

      <main className="content" id="inicio">
        <header className="topbar">
          <strong>OSTOR <span>/ NEXUS</span></strong>
          <span>DIGITAL MUSIC EXPERIENCE</span>
        </header>

        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">◉ EL FUTURO TIENE FRECUENCIA</div>
            <h1>ROMPE EL<br /><em>SILENCIO.</em></h1>
            <p>
              Descubre artistas, explora sonidos y encuentra
              tu próxima obsesión musical.
            </p>

            <form className="search" onSubmit={handleSearch}>
              <input
                aria-label="Buscar música"
                placeholder="Artistas, canciones, géneros..."
                value={query}
                onChange={event => setQuery(event.target.value)}
              />
              <button disabled={loading || !query.trim()}>
                {loading ? 'BUSCANDO...' : 'EXPLORAR →'}
              </button>
            </form>
          </div>

          <div className="hero-visual" aria-hidden="true">
            <div className="record">
              <div className="record-center">OSTOR</div>
            </div>
            <span>FREQUENCY / 002.0</span>
          </div>
        </section>

        <section className="mixes">
          <div className="eyebrow">SESIONES SIN LIMITES</div>
          <h2>OSTOR <span>MIXES</span></h2>
          <p>Sesiones DJ, recopilaciones y musica continua.</p>

          <div className="mix-options">
            {[
              ['DJ SETS', 'dj set live mix'],
              ['ELECTRONICA', 'electronic music mix'],
              ['LOFI', 'lofi hip hop mix'],
              ['REGUETON', 'reggaeton mix'],
              ['CHILL', 'chillout music mix'],
              ['TECHNO', 'techno dj set']
            ].map(([label, search]) => (
              <button
                key={label}
                type="button"
                onClick={async () => {
                  setQuery(search)
                  await runSearch(search)

                  document.getElementById('catalogo')?.scrollIntoView({
                    behavior: 'smooth'
                  })
                }}
              >
                {label} →
              </button>
            ))}
          </div>
        </section>
        <section className="catalog" id="catalogo">
          <div className="catalog-heading">
            <div>
              <div className="eyebrow">EXPLORACIÓN SONORA</div>
              <h2>DESCUBRE <span>EL SONIDO</span></h2>
            </div>
            <small>{visible.length} TRACKS</small>
          </div>

          <div className="filters" aria-label="Filtrar por plataforma">
            {filters.map(source => (
              <button
                key={source}
                className={filter === source ? 'selected' : ''}
                onClick={() => setFilter(source)}
              >
                {source}
              </button>
            ))}
          </div>

          <p className="status" role="status">{message}</p>

          <div className="track-grid">
            {visible.map(track => (
              <button
                type="button"
                className="track-card"
                key={track.id}
                onClick={() => playTrack(track)}
                aria-label={`Reproducir ${track.title}`}
              >
                <div className="artwork">
                  {track.thumbnail
                    ? <img src={track.thumbnail} alt="" loading="lazy" />
                    : <span>♫</span>}
                  <div className="card-arrow">↗</div>
                </div>
                <div className="track-info">
                  <span className="track-source">{track.source}</span>
                  <strong title={track.title}>{track.title}</strong>
                  <small title={track.channel}>{track.channel}</small>
                </div>
              </button>
            ))}
          </div>

          {activeQuery && hasMore && (
            <div className="load-more">
              <button
                type="button"
                className="load-more-button"
                onClick={loadMoreTracks}
                disabled={loading}
              >
                {loading ? 'CARGANDO MUSICA...' : 'CARGAR MAS MUSICA ↓'}
              </button>
            </div>
          )}
          {!loading && visible.length === 0 && (
            <div className="empty">
              No hay canciones para mostrar en este filtro.
            </div>
          )}
        </section>
      </main>
      {currentTrack && (
        <div className="ostor-player" role="region" aria-label="Reproductor OSTOR">
          <div className="player-track">
            {currentTrack.thumbnail && (
              <img src={currentTrack.thumbnail} alt="" />
            )}
            <div>
              <strong>{currentTrack.title}</strong>
              <small>{currentTrack.channel} · {currentTrack.source}</small>
            </div>
          </div>

          <div className="player-controls">
            <button type="button" onClick={previousTrack} aria-label="Anterior">⏮</button>
            <button
              type="button"
              onClick={togglePlayback}
              aria-label={playing ? 'Pausar' : 'Reproducir'}
            >
              {playing ? '⏸' : '▶'}
            </button>
            <button type="button" onClick={nextTrack} aria-label="Siguiente">⏭</button>
            <button type="button" onClick={() => {
              setCurrentTrack(null)
              setPlaying(false)
            }} aria-label="Cerrar reproductor">✕</button>
          </div>

          {currentTrack.stream_url ? (
            <audio
              key={currentTrack.id}
              ref={audioRef}
              src={currentTrack.stream_url}
              controls
              autoPlay
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onEnded={nextTrack}
              onError={() => {
                setPlaying(false)
                setMessage('No se pudo reproducir esta pista. Prueba otra.')
              }}
            />
          ) : (
            <span className="player-unavailable">Audio no disponible</span>
          )}
        </div>
      )}
    </div>
  )
}




