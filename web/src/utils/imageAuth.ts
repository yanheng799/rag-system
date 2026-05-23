/**
 * 图片认证代理：将 /api/v1/images/... 路径转为带 token 的 blob URL，
 * 解决浏览器 <img>/<a-image> 不携带 Authorization header 的问题。
 */

const blobCache = new Map<string, string>()

export async function resolveImageUrl(proxyPath: string): Promise<string> {
  if (blobCache.has(proxyPath)) return blobCache.get(proxyPath)!
  const token = localStorage.getItem('access_token')
  const resp = await fetch(proxyPath, { headers: { Authorization: `Bearer ${token}` } })
  if (!resp.ok) return proxyPath
  const blob = await resp.blob()
  const blobUrl = URL.createObjectURL(blob)
  blobCache.set(proxyPath, blobUrl)
  return blobUrl
}

export function revokeAllImageBlobs(): void {
  blobCache.forEach((blobUrl) => URL.revokeObjectURL(blobUrl))
  blobCache.clear()
}
