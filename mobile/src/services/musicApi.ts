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

const AUDIUS_APP_NAME = 'osto';
const AUDIUS_ENDPOINTS = [
  'https://discoveryprovider.audius.co',
  'https://audius-discovery-1.cultur3stake.com',
  'https://discoveryprovider2.audius.co',
];

async function fetchJson(url: string): Promise<any> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);

  try {
    const response = await fetch(url, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Servicio musical: HTTP ${response.status}`);
    }

    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function firstText(value: unknown, fallback: string): string {
  if (Array.isArray(value)) {
    return firstText(value[0], fallback);
  }

  return typeof value === 'string' && value.trim()
    ? value
    : fallback;
}

async function searchArchive(query: string, limit: number): Promise<Track[]> {
  const params = new URLSearchParams();

  params.append('q', `(${query}) AND mediatype:audio`);

  for (const field of ['identifier', 'title', 'creator', 'description']) {
    params.append('fl[]', field);
  }

  params.append('sort[]', 'downloads desc');
  params.append('rows', String(limit * 4));
  params.append('page', '1');
  params.append('output', 'json');

  const data = await fetchJson(
    `https://archive.org/advancedsearch.php?${params.toString()}`
  );

  const docs = Array.isArray(data?.response?.docs)
    ? data.response.docs
    : [];

  return docs
    .filter((item: any) => typeof item?.identifier === 'string')
    .slice(0, limit)
    .map((item: any): Track => {
      const identifier = item.identifier;

      return {
        id: `archive_${identifier}`,
        title: firstText(item.title, 'Sin titulo').slice(0, 140),
        channel: firstText(item.creator, 'Archive').slice(0, 90),
        description: firstText(item.description, '').slice(0, 600),
        thumbnail: `https://archive.org/services/img/${encodeURIComponent(identifier)}`,
        url: `https://archive.org/details/${encodeURIComponent(identifier)}`,
        source: 'ARCHIVE',
      };
    });
}

async function searchAudius(query: string, limit: number): Promise<Track[]> {
  for (const endpoint of AUDIUS_ENDPOINTS) {
    try {
      const params = new URLSearchParams({
        query,
        app_name: AUDIUS_APP_NAME,
      });

      const data = await fetchJson(
        `${endpoint}/v1/tracks/search?${params.toString()}`
      );

      if (!Array.isArray(data?.data) || data.data.length === 0) {
        continue;
      }

      return data.data
        .filter((item: any) => item?.id)
        .slice(0, limit)
        .map((item: any): Track => {
          const art = item.artwork || {};
          const id = String(item.id);

          return {
            id: `audius_${id}`,
            title: firstText(item.title, 'Track').slice(0, 140),
            channel: firstText(item.user?.name, 'Audius').slice(0, 90),
            description: firstText(item.description, '').slice(0, 600),
            thumbnail: art['1000x1000'] || art['480x480'] || art['150x150'] || '',
            url: item.permalink
              ? `https://audius.co${item.permalink}`
              : `https://audius.co/tracks/${id}`,
            stream_url: `${endpoint}/v1/tracks/${encodeURIComponent(id)}/stream?app_name=${encodeURIComponent(AUDIUS_APP_NAME)}`,
            source: 'AUDIUS',
          };
        });
    } catch {
      // Intentar el siguiente servidor de Audius.
    }
  }

  return [];
}

async function searchProviders(query: string): Promise<Track[]> {
  const results = await Promise.allSettled([
    searchArchive(query, 20),
    searchAudius(query, 20),
  ]);

  const tracks = results.flatMap((result) =>
    result.status === 'fulfilled' ? result.value : []
  );

  if (results.every((result) => result.status === 'rejected')) {
    throw new Error('No se pudo conectar con Archive ni Audius.');
  }

  const seen = new Set<string>();

  return tracks.filter((track) => {
    if (seen.has(track.id)) return false;
    seen.add(track.id);
    return true;
  });
}

export function getTrendingTracks(): Promise<Track[]> {
  return searchProviders('lofi chill jazz');
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

  const tracks = await searchProviders(text);

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
  const identifier = id.slice('archive_'.length);

  if (!identifier || identifier.includes('/') || identifier.includes('\\')) {
    throw new Error('Identificador de Archive no valido.');
  }

  const data = await fetchJson(
    `https://archive.org/metadata/${encodeURIComponent(identifier)}`
  );

  const files = Array.isArray(data?.files) ? data.files : [];

  const audio = files
    .filter((file: any) => {
      const name = String(file?.name || '').toLowerCase();

      return /\.(mp3|m4a)$/.test(name) &&
        !name.includes('spectrogram') &&
        !name.includes('waveform');
    })
    .sort((a: any, b: any) =>
      (Number(b.size) || 0) - (Number(a.size) || 0)
    );

  if (audio.length === 0) {
    throw new Error('Archive no contiene audio compatible.');
  }

  const fileName = String(audio[0].name);
  const encodedFile = fileName
    .split('/')
    .map((part) => encodeURIComponent(part))
    .join('/');

  const uri =
    `https://archive.org/download/${encodeURIComponent(identifier)}/${encodedFile}`;

  archiveStreamCache.set(id, {
    uri,
    expiresAt: Date.now() + ARCHIVE_CACHE_MS,
  });

  return uri;
}