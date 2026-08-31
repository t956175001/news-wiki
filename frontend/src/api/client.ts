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

// Shown when the request never reached the server. axios only has its own
// English string for these ("Network Error", "timeout of 30000ms exceeded"),
// which used to be rendered straight into a page that is otherwise Chinese.
const TIMEOUT_DETAIL = '请求超时，请检查网络后重试。'
const OFFLINE_DETAIL = '网络连接失败，请检查网络后重试。'

export function normalizeApiError(error: AxiosError<ApiErrorBody>) {
  const body = error.response?.data
  if (body?.code || body?.detail) {
    return Promise.reject(new ApiError(body.code ?? 'NETWORK_ERROR', body.detail ?? '请求失败'))
  }

  // No response body to speak of. Either the server answered with something
  // that is not our error envelope, or it never answered at all.
  if (error.response) {
    return Promise.reject(
      new ApiError('SERVER_ERROR', `服务异常（HTTP ${error.response.status}）。`),
    )
  }
  const timedOut = error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT'
  return Promise.reject(new ApiError('NETWORK_ERROR', timedOut ? TIMEOUT_DETAIL : OFFLINE_DETAIL))
}

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use((response) => response, normalizeApiError)

export default client
