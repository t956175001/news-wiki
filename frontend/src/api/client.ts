import axios, { AxiosError } from 'axios'

export class ApiError extends Error {
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

export interface ApiErrorBody {
  code?: string
  detail?: string
}

export function normalizeApiError(error: AxiosError<ApiErrorBody>) {
  const body = error.response?.data
  const code = body?.code ?? 'NETWORK_ERROR'
  const detail = body?.detail ?? error.message ?? '请求失败'
  return Promise.reject(new ApiError(code, detail))
}

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use((response) => response, normalizeApiError)

export default client
