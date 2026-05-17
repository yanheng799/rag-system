import request from './request'

export interface ChunkListItem {
  chunk_id: string
  doc_id: string
  chunk_type: string
  page: number
  chunk_index: number
  char_count: number
  full_text: string
  element_count: number
  image_urls: string[]
  group_id: string
  created_at: string | null
}

export interface ChunkListResponse {
  total: number
  page: number
  size: number
  items: ChunkListItem[]
}

export interface ChunkDetail {
  chunk_id: string
  doc_id: string
  chunk_type: string
  page: number
  chunk_index: number
  char_count: number
  full_text: string
  elements: { type: string; content: string; image_url?: string }[]
  image_urls: string[]
  group_id: string
  created_at: string | null
}

export interface EditChunkResponse {
  chunk_id: string
  full_text: string
  char_count: number
}

export interface MergeResponse {
  merged_chunk_id: string
  deleted_chunk_ids: string[]
  char_count: number
}

export interface SplitResponse {
  chunk_a: { chunk_id: string; char_count: number; element_count: number }
  chunk_b: { chunk_id: string; char_count: number; element_count: number }
  deleted_chunk_id: string
}

export interface LinkResponse {
  group_id: string
  chunk_ids: string[]
}

export interface UnlinkResponse {
  unlinked_count: number
}

export const listChunks = (docId: string, params: { page?: number; size?: number }) =>
  request.get<any, ChunkListResponse>(`/documents/${docId}/chunks`, { params })

export const getChunkDetail = (chunkId: string) =>
  request.get<any, ChunkDetail>(`/chunks/${chunkId}`)

export const editChunk = (chunkId: string, fullText: string) =>
  request.put<any, EditChunkResponse>(`/chunks/${chunkId}`, { full_text: fullText })

export const deleteChunk = (chunkId: string) =>
  request.delete<any, { message: string; chunk_id: string }>(`/chunks/${chunkId}`)

export const mergeChunks = (chunkIds: string[]) =>
  request.post<any, MergeResponse>('/chunks/merge', { chunk_ids: chunkIds })

export const splitChunk = (chunkId: string, splitAt: number, linkGroup = false) =>
  request.post<any, SplitResponse>(`/chunks/${chunkId}/split`, {
    split_at: splitAt,
    link_group: linkGroup,
  })

export const linkChunks = (chunkIds: string[]) =>
  request.post<any, LinkResponse>('/chunks/link', { chunk_ids: chunkIds })

export const unlinkChunks = (chunkIds: string[]) =>
  request.post<any, UnlinkResponse>('/chunks/unlink', { chunk_ids: chunkIds })
