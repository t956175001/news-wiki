import { describe, it, expect } from 'vitest'
import { AxiosError, AxiosHeaders } from 'axios'
import { normalizeApiError, ApiError, type ApiErrorBody } from './client'

function makeError(response?: { status: number; data: ApiErrorBody }, code?: string) {
  return new AxiosError<ApiErrorBody>(
    'Request failed',
    code,
    undefined,
    undefined,
    response && {
      status: response.status,
      data: response.data,
      statusText: '',
      headers: new AxiosHeaders(),
      config: { headers: new AxiosHeaders() },
    },
  )
}

describe('normalizeApiError', () => {
  it('rejects with an ApiError carrying the backend code and detail', async () => {
    const error = makeError({ status: 400, data: { code: 'INVALID_INPUT', detail: '参数错误' } })

    await expect(normalizeApiError(error)).rejects.toMatchObject({
      code: 'INVALID_INPUT',
      message: '参数错误',
    })
  })

  it('falls back to NETWORK_ERROR when there is no response body', async () => {
    const error = makeError()

    const rejection = normalizeApiError(error)
    await expect(rejection).rejects.toBeInstanceOf(ApiError)
    await expect(rejection).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  })

  it('does not leak axios English into a page that is otherwise Chinese', async () => {
    // "Network Error" used to be rendered verbatim by every view's error state.
    const offline = makeError()

    await expect(normalizeApiError(offline)).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      message: '网络连接失败，请检查网络后重试。',
    })
  })

  it('tells a timeout apart from an unreachable server', async () => {
    const timedOut = makeError(undefined, 'ECONNABORTED')

    await expect(normalizeApiError(timedOut)).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      message: '请求超时，请检查网络后重试。',
    })
  })

  it('handles a server error that is not in the project error envelope', async () => {
    // A 502 from the reverse proxy, or a Django 500 page — HTML, not our JSON.
    const gatewayError = makeError({ status: 502, data: {} as ApiErrorBody })

    await expect(normalizeApiError(gatewayError)).rejects.toMatchObject({
      code: 'SERVER_ERROR',
      message: '服务异常（HTTP 502）。',
    })
  })
})
