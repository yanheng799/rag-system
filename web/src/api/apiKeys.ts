import request from './request'

export interface ApiKeyItem {
  key_id: string
  name: string | null
  key_prefix: string
  org_id: string
  created_at: string
  expires_at: string | null
  last_used_at: string | null
}

export interface CreateApiKeyResponse extends ApiKeyItem {
  key: string
}

export async function createApiKey(data: {
  name?: string
  org_id: string
  expires_at?: string
}): Promise<CreateApiKeyResponse> {
  return request.post('/api-keys', data)
}

export async function listApiKeys(): Promise<ApiKeyItem[]> {
  return request.get('/api-keys')
}

export async function revokeApiKey(keyId: string): Promise<{ revoked: boolean }> {
  return request.delete(`/api-keys/${keyId}`)
}
