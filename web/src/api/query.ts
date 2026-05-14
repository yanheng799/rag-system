import request from './request'

export interface QueryRequest {
  question: string
  top_k?: number
  dataset_ids?: string[]
  doc_ids?: string[]
  doc_names?: string[]
}

export interface ElementSchema {
  type: string
  content: string
  image_url: string | null
}

export interface ChunkMetadataSchema {
  chunk_id: string
  chunk_type: string
  filename: string
  page: number
  chunk_index: number
  char_count: number
  created_at: string
  doc_id: string
  score: number
}

export interface SourceSchema {
  metadata: ChunkMetadataSchema
  elements: ElementSchema[]
}

export interface QueryResponse {
  answer: string
  sources: SourceSchema[]
  total_ms: number
}

export const queryRag = (data: QueryRequest) =>
  request.post<any, QueryResponse>('/query', data)
