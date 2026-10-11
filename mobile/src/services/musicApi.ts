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

const searchResultCache = new Map<string, { tracks: Track[]; expiresAt: number }>();
const SEARCH_CACHE_MS = 2 * 60 * 1000;
const SEARCH_CACHE_LIMIT = 30;

export async function searchTracks(query: string): Promise<Track[]> {
  const text = query.trim();

  if (!text) return [];

  const key = text.toLocaleLowerCase();
  const cached = searchResultCache.get(key);

  if (cached && cached.expiresAt > Date.now()) {
    return cached.tracks;
  }

  const tracks = await getTracks(`/api/search?q=${encodeURIComponent(text)}&page=1`);

  searchResultCache.delete(key);
  searchResultCache.set(key, {
    tracks,
    expiresAt: Date.now() + SEARCH_CACHE_MS,
  });

  if (searchResultCache.size > SEARCH_CACHE_LIMIT) {
    const oldestKey = searchResultCache.keys().next().value;
    if (oldestKey !== undefined) searchResultCache.delete(oldestKey);
  }

  return tracks;
}

const archiveStreamCache = new Map<string, { uri: string; expiresAt: number }>();
const ARCHIVE_CACHE_MS = 10 * 60 * 1000;

const archivePendingRequests = new Map<string, Promise<string>>();
export function resolveArchiveTrack(id: string): Promise<string> {
  if (!id.startsWith('archive_')) {
    return Promise.reject(new Error('Identificador de Archive no valido.'));
  }

  const cached = archiveStreamCache.get(id);
  if (cached && cached.expiresAt > Date.now()) {
    return Promise.resolve(cached.uri);
  }

  const pending = archivePendingRequests.get(id);
  if (pending) return pending;

  const request = fetchArchiveStream(id);
  archivePendingRequests.set(id, request);

  void request.then(
    () => archivePendingRequests.delete(id),
    () => archivePendingRequests.delete(id)
  );

  return request;
}

async function fetchArchiveStream(id: string): Promise<string> {
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

  archiveStreamCache.set(id, {
    uri: data.stream_url,
    expiresAt: Date.now() + ARCHIVE_CACHE_MS,
  });

  return data.stream_url;
}
