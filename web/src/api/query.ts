import request from './request'

export interface QueryRequest {
  question: string
  top_k?: number
  dataset_ids?: string[]
  doc_ids?: string[]
  doc_names?: string[]
  show_rewritten?: boolean
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
  rewritten_queries?: string[]
}

export interface StreamCallbacks {
  onStatus?: (phase: string) => void
  onToken?: (content: string) => void
  onResult?: (data: { sources: SourceSchema[]; total_ms: number; rewritten_queries?: string[] }) => void
  onError?: (error: Error) => void
}

export async function queryRagStream(data: QueryRequest, callbacks: StreamCallbacks): Promise<void> {
  const token = localStorage.getItem('access_token')
  const baseUrl = (request.defaults?.baseURL || '').replace(/\/$/, '')

  try {
    const response = await fetch(`${baseUrl}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      const errBody = await response.json().catch(() => ({ detail: response.statusText }))
      throw new Error(errBody.detail || `请求失败: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('浏览器不支持流式响应')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let currentEvent = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const rawData = line.slice(6)
          try {
            const payload = JSON.parse(rawData)
            switch (currentEvent) {
              case 'status':
                callbacks.onStatus?.(payload.phase)
                break
              case 'token':
                callbacks.onToken?.(payload.content)
                break
              case 'result':
                callbacks.onResult?.(payload)
                break
            }
          } catch {
            // skip malformed data
          }
          currentEvent = ''
        }
      }
    }
  } catch (e) {
    callbacks.onError?.(e instanceof Error ? e : new Error(String(e)))
  }
}
