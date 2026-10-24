export type MusicSource =
  | 'ARCHIVE'
  | 'AUDIUS'
  | 'JAMENDO'
  | 'YOUTUBE'

export interface Track {
  id: string
  title: string
  channel: string
  description?: string
  thumbnail?: string
  url?: string
  stream_url?: string
  video_id?: string
  source: MusicSource
}
