export type MusicSource =
  | 'ARCHIVE'
  | 'AUDIUS'
  | 'JAMENDO'

export interface Track {
  id: string
  title: string
  channel: string
  description?: string
  thumbnail?: string
  url?: string
  stream_url?: string
  source: MusicSource
}
