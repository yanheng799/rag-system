import request from './request'

export interface DatasetCreateRequest {
  name: string
  description?: string
}

export interface DatasetUpdateRequest {
  name?: string
  description?: string
}

export interface DatasetResponse {
  dataset_id: string
  name: string
  description: string | null
  doc_count: number
  created_at: string | null
  updated_at: string | null
}

export interface DatasetListResponse {
  total: number
  page: number
  size: number
  items: DatasetResponse[]
}

export const createDataset = (data: DatasetCreateRequest) =>
  request.post<any, DatasetResponse>('/datasets', data)

export const listDatasets = (params: { page?: number; size?: number }) =>
  request.get<any, DatasetListResponse>('/datasets', { params })

export const getDataset = (datasetId: string) =>
  request.get<any, DatasetResponse>(`/datasets/${datasetId}`)

export const updateDataset = (datasetId: string, data: DatasetUpdateRequest) =>
  request.patch<any, DatasetResponse>(`/datasets/${datasetId}`, data)

export const deleteDataset = (datasetId: string, force = false) =>
  request.delete<any, { message: string; dataset_id: string }>(`/datasets/${datasetId}`, { params: { force } })
