import request from './request'
import axios from 'axios'

export interface UploadResponse {
  doc_id: string
  filename: string
  dataset_id: string | null
  status: string
  uploaded_at: string
}

export interface DocumentStatusResponse {
  doc_id: string
  filename: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  error_msg: string | null
  uploaded_at: string | null
  updated_at: string | null
}

export interface IngestResult {
  doc_id: string
  filename: string
  status: string
  error_msg: string | null
}

export interface IngestResponse {
  results: IngestResult[]
}

export const uploadDocuments = (files: File[], datasetId?: string) => {
  const formData = new FormData()
  files.forEach((f) => formData.append('files', f))
  if (datasetId) formData.append('dataset_id', datasetId)
  return axios.post<any, UploadResponse[]>('/api/v1/documents', formData, {
    timeout: 120000,
  })
}

export const ingestDocuments = (docIds: string[]) =>
  request.post<any, IngestResponse>('/documents/ingest', { doc_ids: docIds })

export const getDocumentStatus = (docId: string) =>
  request.get<any, DocumentStatusResponse>(`/documents/${docId}/status`)

export const deleteDocument = (docId: string) =>
  request.delete<any, { message: string; doc_id: string }>(`/documents/${docId}`)

export interface DocumentListItem {
  doc_id: string
  filename: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  error_msg: string | null
  uploaded_at: string | null
  updated_at: string | null
}

export interface DocumentListResponse {
  total: number
  page: number
  size: number
  items: DocumentListItem[]
}

export const listDocuments = (params?: { dataset_id?: string; page?: number; size?: number }) =>
  request.get<any, DocumentListResponse>('/documents', { params })
