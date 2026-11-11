import axios from 'axios'

// 统一 axios 实例,baseURL 走 Vite 代理
export const httpClient = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

/** 从 axios 错误中提取可读信息 */
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    return typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((item: { msg?: string }) => item.msg ?? '请求参数无效').join('；')
        : error.message
  }
  return error instanceof Error ? error.message : String(error)
}
