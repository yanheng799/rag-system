import request from './request'

export interface RetrieveRequest {
  question: string
  top_k?: number
  search_mode?: 'vector' | 'bm25' | 'hybrid'
  dataset_ids?: string[]
  doc_ids?: string[]
  doc_names?: string[]
}

export interface ChunkScores {
  vector_score: number
  bm25_score: number
  rrf_score: number | null
}

export interface ChunkMetadataResult {
  chunk_id: string
  chunk_type: string
  filename: string
  page: number
  pages: number[]
  chunk_index: number
  char_count: number
  created_at: string
  doc_id: string
}

export interface RetrievedChunkResult {
  rank: number
  metadata: ChunkMetadataResult
  full_text: string
  scores: ChunkScores
  image_urls: string[]
}

export interface RetrieveResponse {
  question: string
  search_mode: string
  total_retrieved: number
  retrieval_ms: number
  chunks: RetrievedChunkResult[]
}

export const retrieveChunks = (data: RetrieveRequest) =>
  request.post<any, RetrieveResponse>('/retrieve', data)
