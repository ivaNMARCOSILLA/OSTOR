import React, { useEffect, useRef, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { WebView } from 'react-native-webview';
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { getTrendingTracks, searchTracks, resolveArchiveTrack, type Track } from './src/services/musicApi';
import {
  ActivityIndicator,
  Image,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

type Tab = 'Descubrir' | 'Buscar' | 'Favoritos';

const CYAN = '#00e5ff';
const PURPLE = '#854bff';
const MAGENTA = '#ff2fd6';

export default function App() {
  const [tab, setTab] = useState<Tab>('Descubrir');
  const [query, setQuery] = useState('');

  // ELECTRONICAMA 033F - Catalogo real
  const [tracks, setTracks] = useState<Track[]>([]);
  const [favorites, setFavorites] = useState<Track[]>([]);
  const [favoritesLoaded, setFavoritesLoaded] = useState(false);

  useEffect(() => {
    let active = true;

    AsyncStorage.getItem('electronicama:favorites:v1')
      .then((stored) => {
        if (!active || !stored) return;

        const parsed: unknown = JSON.parse(stored);

        if (!Array.isArray(parsed)) return;

        const valid = parsed.filter(
          (item): item is Track =>
            typeof item === 'object' &&
            item !== null &&
            typeof item.id === 'string' &&
            typeof item.title === 'string' &&
            typeof item.channel === 'string' &&
            ['ARCHIVE', 'AUDIUS', 'YOUTUBE'].includes(item.source)
        );

        setFavorites(valid);
      })
      .catch(() => {
        if (active) {
          setPlayerError('No se pudieron cargar los favoritos.');
        }
      })
      .finally(() => {
        if (active) setFavoritesLoaded(true);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!favoritesLoaded) return;

    void AsyncStorage.setItem(
      'electronicama:favorites:v1',
      JSON.stringify(favorites)
    ).catch(() => {
      setPlayerError('No se pudieron guardar los favoritos.');
    });
  }, [favorites, favoritesLoaded]);

  function toggleFavorite(track: Track) {
    setFavorites((previous) =>
      previous.some((item) => item.id === track.id)
        ? previous.filter((item) => item.id !== track.id)
        : [...previous, track]
    );
  }
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentTrack, setCurrentTrack] = useState<Track | null>(null);
  const [youtubeTrack, setYoutubeTrack] = useState<Track | null>(null);
  const [playerError, setPlayerError] = useState('');
  const playRequest = useRef(0);
  const player = useAudioPlayer(null);
  const playerStatus = useAudioPlayerStatus(player);

  useEffect(() => {
    void setAudioModeAsync({
      playsInSilentMode: true,
      shouldPlayInBackground: true,
    }).catch(() => {
      setPlayerError('No se pudo configurar el audio del dispositivo.');
    });
  }, []);

  async function playTrack(track: Track) {
    const requestId = ++playRequest.current;

    if (track.source === 'YOUTUBE') {
      if (!track.video_id || !/^[A-Za-z0-9_-]{11}$/.test(track.video_id)) {
        setPlayerError('Este video de YouTube no tiene un identificador valido.');
        return;
      }

      setPlayerError('');
      player.pause();
      setCurrentTrack(null);
      setYoutubeTrack(track);
      return;
    }

    setYoutubeTrack(null);
    setPlayerError('');
    player.pause();
    setCurrentTrack(null);

    try {
      let uri = track.stream_url;

      if (!uri && track.source === 'ARCHIVE') {
        uri = await resolveArchiveTrack(track.id);
      }

      if (requestId !== playRequest.current) return;

      if (!uri || !uri.startsWith('https://')) {
        throw new Error('No hay un enlace directo de audio disponible.');
      }

      player.replace({ uri });
      setCurrentTrack(track);
      player.play();
    } catch (cause) {
      if (requestId !== playRequest.current) return;

      setPlayerError(
        cause instanceof Error
          ? cause.message
          : 'No se pudo iniciar la reproduccion.'
      );
    }
  }

  function togglePlayback() {
    if (!currentTrack) return;

    if (!playerStatus.isLoaded || playerStatus.error) {
      setPlayerError(
        playerStatus.error || 'El audio todavia no esta preparado.'
      );
      return;
    }

    try {
      if (playerStatus.playing) {
        player.pause();
      } else {
        player.play();
      }
    } catch {
      setPlayerError('No se pudo cambiar la reproduccion.');
    }
  }

  function changeTrack(direction: number) {
    if (!currentTrack) return;

    const playable = tracks.filter(
      (track) =>
        track.source !== 'YOUTUBE' &&
        (!!track.stream_url || track.source === 'ARCHIVE')
    );

    const index = playable.findIndex(
      (track) => track.id === currentTrack.id
    );

    if (index < 0 || playable.length === 0) return;

    const next = (index + direction + playable.length) % playable.length;
    playTrack(playable[next]);
  }

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError('');

      try {
        const results = query.trim()
          ? await searchTracks(query)
          : await getTrendingTracks();

        if (active) setTracks(results);
      } catch (cause) {
        if (active) {
          setTracks([]);
          setError(
            cause instanceof Error ? cause.message : 'Error de conexion'
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    const timeout = setTimeout(() => { void load(); }, query.trim() ? 450 : 0);

    return () => {
      active = false;
      clearTimeout(timeout);
    };
  }, [query]);


  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar barStyle="light-content" backgroundColor="#050509" />

      <View style={styles.header}>
        <Text style={styles.eyebrow}>EL SONIDO DEL FUTURO</Text>
        <Text style={styles.brand}>ELECTRONICAMA</Text>
        <View style={styles.ledLine} />
      </View>

      <ScrollView
        style={styles.content}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.hero}>
          <Text style={styles.heroLabel}>TU UNIVERSO ELECTRÓNICO</Text>
          <Text style={styles.heroTitle}>
            Siente cada{'\n'}
            <Text style={styles.highlight}>frecuencia.</Text>
          </Text>
          <Text style={styles.heroDescription}>
            Techno, house, trance y sonidos que no conocen límites.
          </Text>
        </View>

        <View style={styles.searchBox}>
          <Text style={styles.searchIcon}>⌕</Text>
          <TextInput
            style={styles.input}
            value={query}
            onChangeText={setQuery}
            onFocus={() => setTab('Buscar')}
            placeholder="Busca artistas, temas o estilos..."
            placeholderTextColor="#85859a"
            returnKeyType="search"
          />
        </View>

        <Text style={styles.sectionTitle}>
          {tab === 'Favoritos'
            ? 'TUS FAVORITOS'
            : tab === 'Buscar'
              ? 'EXPLORA LA MÚSICA'
              : 'DESCUBRE TU SONIDO'}
        </Text>

        <View style={styles.featureCard}>
          <View style={styles.record}>
            <View style={styles.recordRing}>
              <View style={styles.recordCenter} />
            </View>
          </View>
          <View style={styles.featureText}>
            <Text style={styles.cardLabel}>ELECTRONICAMA RADIO</Text>
            <Text style={styles.cardTitle}>La noche es tuya</Text>
            <Text style={styles.cardDescription}>
              Tu próxima sesión comienza aquí.
            </Text>
          </View>
        </View>

        <View style={{ marginBottom: 22 }}>
          <Text style={styles.sectionTitle}>
            {tab === 'Favoritos'
              ? 'CANCIONES GUARDADAS'
              : query.trim()
                ? 'RESULTADOS DE BUSQUEDA'
                : 'TENDENCIAS'}
          </Text>

          {tab !== 'Favoritos' && loading && (
            <ActivityIndicator size="large" color={CYAN} />
          )}

          {tab !== 'Favoritos' && !!error && (
            <Text style={{ color: MAGENTA, marginBottom: 12 }}>
              {error}
            </Text>
          )}

          {tab === 'Favoritos' && favoritesLoaded && favorites.length === 0 && (
            <Text style={{ color: '#a4a2b5' }}>
              Todavia no tienes canciones favoritas.
            </Text>
          )}

          {tab !== 'Favoritos' && !loading && !error && tracks.length === 0 && (
            <Text style={{ color: '#a4a2b5' }}>
              No hay canciones disponibles.
            </Text>
          )}

          {(tab === 'Favoritos' ? favorites : tracks).map((track) => (
            <TouchableOpacity
              onPress={() => playTrack(track)}
              accessibilityRole="button"
              accessibilityLabel={`Reproducir ${track.title}`}
              activeOpacity={0.75}
              key={track.id}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                backgroundColor: '#11111d',
                borderWidth: 1,
                borderColor: '#34234f',
                borderRadius: 14,
                padding: 10,
                marginBottom: 10,
              }}
            >
              {track.thumbnail ? (
                <Image
                  source={{ uri: track.thumbnail }}
                  style={{
                    width: 58,
                    height: 58,
                    borderRadius: 9,
                    marginRight: 12,
                  }}
                />
              ) : (
                <View
                  style={{
                    width: 58,
                    height: 58,
                    borderRadius: 9,
                    backgroundColor: '#26203d',
                    marginRight: 12,
                  }}
                />
              )}

              <View style={{ flex: 1 }}>
                <Text
                  numberOfLines={1}
                  style={{ color: '#fff', fontWeight: '800', fontSize: 14 }}
                >
                  {track.title}
                </Text>
                <Text
                  numberOfLines={1}
                  style={{ color: '#aaa5ba', marginTop: 5, fontSize: 12 }}
                >
                  {track.channel}
                </Text>
                <Text
                  style={{
                    color: CYAN,
                    fontSize: 10,
                    marginTop: 5,
                    fontWeight: '800',
                  }}
                >
                  {track.source}
                </Text>
              </View>
              <TouchableOpacity
                onPress={(event) => {
                  event.stopPropagation();
                  toggleFavorite(track);
                }}
                accessibilityRole="button"
                accessibilityLabel={
                  favorites.some((item) => item.id === track.id)
                    ? 'Quitar de favoritos'
                    : 'A\u00f1adir a favoritos'
                }
                style={{ padding: 10 }}
              >
                <Text
                  style={{
                    color: favorites.some((item) => item.id === track.id)
                      ? MAGENTA
                      : '#77718c',
                    fontSize: 25,
                  }}
                >
                  {favorites.some((item) => item.id === track.id)
                    ? '\u2665'
                    : '\u2661'}
                </Text>
              </TouchableOpacity>
              <Text style={{ color: CYAN, fontSize: 24, marginLeft: 4 }}>
                {'\u25b6'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.infoCard}>
          <Text style={styles.infoTitle}>UNA EXPERIENCIA SIN LÍMITES</Text>
          <Text style={styles.infoDescription}>
            Estamos preparando el catálogo musical, las listas,
            los favoritos y el reproductor nativo.
          </Text>
          <View style={styles.sourceRow}>
            <Text style={styles.source}>AUDIUS</Text>
            <Text style={styles.source}>ARCHIVE</Text>
            <Text style={styles.source}>YOUTUBE</Text>
          </View>
        </View>
      </ScrollView>

      {!!(playerError || (currentTrack && playerStatus.error)) && (
        <Text style={{
          color: MAGENTA,
          paddingHorizontal: 18,
          paddingVertical: 8,
          backgroundColor: '#160c1c',
          fontSize: 12,
        }}>
          {playerError || playerStatus.error}
        </Text>
      )}

      {currentTrack && (
        <View style={{
          backgroundColor: '#151024',
          borderTopWidth: 1,
          borderTopColor: PURPLE,
          paddingHorizontal: 14,
          paddingVertical: 12,
          flexDirection: 'row',
          alignItems: 'center',
        }}>
          {currentTrack.thumbnail ? (
            <Image
              source={{ uri: currentTrack.thumbnail }}
              style={{ width: 44, height: 44, borderRadius: 7, marginRight: 10 }}
            />
          ) : null}
          <View style={{ flex: 1, marginRight: 10 }}>
            <Text
              numberOfLines={1}
              style={{ color: '#fff', fontWeight: '800', fontSize: 13 }}
            >
              {currentTrack.title}
            </Text>
            <Text
              numberOfLines={1}
              style={{ color: CYAN, fontSize: 11, marginTop: 3 }}
            >
              {currentTrack.channel}
            </Text>
            <Text
              numberOfLines={1}
              style={{ color: '#aaa4c0', fontSize: 10, marginTop: 3 }}
            >
              {playerStatus.error
                ? 'Error de reproduccion'
                : playerStatus.isBuffering
                    ? 'Cargando audio...'
                    : !playerStatus.isLoaded
                    ? 'Cargando audio...'
                    : playerStatus.playing
                      ? 'Reproduciendo'
                      : 'En pausa'}
            </Text>
          </View>

          <TouchableOpacity
            onPress={() => changeTrack(-1)}
            accessibilityLabel="Cancion anterior"
            style={{ padding: 10 }}
          >
            <Text style={{ color: '#fff', fontSize: 20 }}>{'\u23EE'}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={togglePlayback}
            accessibilityLabel={playerStatus.playing ? 'Pausar' : 'Reproducir'}
            style={{ padding: 10 }}
          >
            <Text style={{ color: CYAN, fontSize: 25 }}>
              {playerStatus.playing ? '\u23F8' : '\u25B6'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => changeTrack(1)}
            accessibilityLabel="Cancion siguiente"
            style={{ padding: 10 }}
          >
            <Text style={{ color: '#fff', fontSize: 20 }}>{'\u23ED'}</Text>
          </TouchableOpacity>
        </View>
      )}

      {youtubeTrack?.video_id && (
        <View
          style={{
            marginHorizontal: 16,
            marginBottom: 12,
            borderWidth: 1,
            borderColor: PURPLE,
            borderRadius: 14,
            backgroundColor: '#10101c',
            overflow: 'hidden',
          }}
        >
          <View
            style={{
              paddingHorizontal: 12,
              paddingVertical: 10,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <Text
              numberOfLines={1}
              style={{ color: '#ffffff', fontWeight: '700', flex: 1 }}
            >
              {youtubeTrack.title}
            </Text>
            <TouchableOpacity
              onPress={() => setYoutubeTrack(null)}
              accessibilityRole="button"
              accessibilityLabel="Cerrar reproductor de YouTube"
              style={{ padding: 8 }}
            >
              <Text style={{ color: CYAN, fontWeight: '800' }}>CERRAR</Text>
            </TouchableOpacity>
          </View>
          <WebView
            key={youtubeTrack.video_id}
            source={{
              uri: `https://www.youtube.com/embed/${youtubeTrack.video_id}?playsinline=1`,
            }}
            style={{ height: 220, backgroundColor: '#000000' }}
            javaScriptEnabled
            domStorageEnabled
            allowsInlineMediaPlayback
            mediaPlaybackRequiresUserAction
            originWhitelist={['https://*']}
          />
        </View>
      )}

      <View style={styles.bottomNav}>
        {(['Descubrir', 'Buscar', 'Favoritos'] as Tab[]).map((item) => (
          <TouchableOpacity
            key={item}
            style={styles.navItem}
            onPress={() => setTab(item)}
            accessibilityRole="tab"
            accessibilityState={{ selected: tab === item }}
          >
            <Text style={[
              styles.navSymbol,
              tab === item && styles.navActive,
            ]}>
              {item === 'Descubrir' ? '◈' : item === 'Buscar' ? '⌕' : '♡'}
            </Text>
            <Text style={[
              styles.navText,
              tab === item && styles.navActive,
            ]}>
              {item}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#050509',
  },
  header: {
    paddingHorizontal: 22,
    paddingTop: 22,
    paddingBottom: 14,
    backgroundColor: '#090910',
  },
  eyebrow: {
    color: '#9992b9',
    fontSize: 9,
    letterSpacing: 3,
    fontWeight: '700',
    marginBottom: 8,
  },
  brand: {
    color: '#ffffff',
    fontSize: 25,
    fontWeight: '900',
    letterSpacing: 1.2,
  },
  ledLine: {
    height: 2,
    marginTop: 15,
    backgroundColor: CYAN,
    borderRadius: 8,
    shadowColor: CYAN,
    shadowOpacity: 0.95,
    shadowRadius: 12,
    elevation: 8,
  },
  content: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingTop: 24,
    paddingBottom: 36,
  },
  hero: {
    paddingVertical: 22,
  },
  heroLabel: {
    color: MAGENTA,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 2.1,
    marginBottom: 16,
  },
  heroTitle: {
    color: '#ffffff',
    fontSize: 39,
    fontWeight: '900',
    lineHeight: 45,
  },
  highlight: {
    color: CYAN,
  },
  heroDescription: {
    color: '#a4a2b5',
    fontSize: 14,
    lineHeight: 22,
    marginTop: 16,
  },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: PURPLE,
    backgroundColor: '#11111d',
    borderRadius: 16,
    paddingHorizontal: 16,
    marginBottom: 32,
  },
  searchIcon: {
    color: CYAN,
    fontSize: 30,
    marginRight: 10,
  },
  input: {
    flex: 1,
    color: '#ffffff',
    fontSize: 14,
    paddingVertical: 17,
  },
  sectionTitle: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '900',
    letterSpacing: 1.3,
    marginBottom: 16,
  },
  featureCard: {
    borderRadius: 22,
    borderWidth: 1,
    borderColor: PURPLE,
    backgroundColor: '#151024',
    minHeight: 186,
    padding: 20,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 18,
  },
  record: {
    width: 112,
    height: 112,
    borderRadius: 56,
    backgroundColor: '#080910',
    borderWidth: 3,
    borderColor: '#35344d',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 18,
  },
  recordRing: {
    width: 75,
    height: 75,
    borderRadius: 40,
    borderWidth: 2,
    borderColor: CYAN,
    alignItems: 'center',
    justifyContent: 'center',
  },
  recordCenter: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: MAGENTA,
  },
  featureText: {
    flex: 1,
  },
  cardLabel: {
    color: CYAN,
    fontSize: 9,
    letterSpacing: 1.5,
    fontWeight: '800',
    marginBottom: 12,
  },
  cardTitle: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '900',
    marginBottom: 9,
  },
  cardDescription: {
    color: '#a6a2b9',
    fontSize: 12,
    lineHeight: 19,
  },
  infoCard: {
    borderWidth: 1,
    borderColor: '#38304f',
    borderRadius: 20,
    padding: 20,
    backgroundColor: '#0f0e18',
  },
  infoTitle: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 0.8,
    marginBottom: 12,
  },
  infoDescription: {
    color: '#a4a2b5',
    fontSize: 13,
    lineHeight: 21,
  },
  sourceRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 9,
    marginTop: 20,
  },
  source: {
    color: CYAN,
    fontSize: 10,
    fontWeight: '800',
    borderWidth: 1,
    borderColor: '#22535f',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  bottomNav: {
    flexDirection: 'row',
    backgroundColor: '#0c0b14',
    borderTopWidth: 1,
    borderTopColor: '#34234f',
    paddingTop: 12,
    paddingBottom: 16,
  },
  navItem: {
    flex: 1,
    alignItems: 'center',
    gap: 5,
  },
  navSymbol: {
    color: '#777389',
    fontSize: 23,
  },
  navText: {
    color: '#777389',
    fontSize: 11,
    fontWeight: '700',
  },
  navActive: {
    color: CYAN,
  },
});
