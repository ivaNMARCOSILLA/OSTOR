export type MusicSource = 'ARCHIVE' | 'AUDIUS';

export interface Track {
  id: string;
  title: string;
  channel: string;
  description?: string;
  thumbnail?: string;
  url?: string;
  stream_url?: string;

  source: MusicSource;
}

const API_BASE = 'https://www.electronicama.com';

async function getTracks(path: string): Promise<Track[]> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Servidor musical: HTTP ${response.status}`);
  }

  const contentType = response.headers.get('content-type') || '';

  if (!contentType.includes('application/json')) {
    throw new Error('El servidor no devolvio datos musicales JSON.');
  }

  const data: unknown = await response.json();

  if (!Array.isArray(data)) {
    throw new Error('Formato de catalogo no valido.');
  }

  return (data as Track[]).filter((track) => track.source === 'ARCHIVE' || track.source === 'AUDIUS');
}

export function getTrendingTracks(): Promise<Track[]> {
  return getTracks('/api/trending');
}

export function searchTracks(query: string): Promise<Track[]> {
  const text = query.trim();

  if (!text) return Promise.resolve([]);

  return getTracks(`/api/search?q=${encodeURIComponent(text)}&page=1`);
}

export async function resolveArchiveTrack(id: string): Promise<string> {
  if (!id.startsWith('archive_')) {
    throw new Error('Identificador de Archive no valido.');
  }

  const response = await fetch(
    `https://www.electronicama.com/api/resolve/${encodeURIComponent(id)}`
  );

  if (!response.ok) {
    throw new Error(`No se pudo resolver Archive: HTTP ${response.status}`);
  }

  const data: unknown = await response.json();

  if (
    typeof data !== 'object' ||
    data === null ||
    !('stream_url' in data) ||
    typeof data.stream_url !== 'string' ||
    !data.stream_url.startsWith('https://')
  ) {
    throw new Error('Archive no ha devuelto un enlace de audio valido.');
  }

  return data.stream_url;
}
