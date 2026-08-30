import { describe, it, expect } from 'vitest'
import { AxiosError, AxiosHeaders } from 'axios'
import { normalizeApiError, ApiError, type ApiErrorBody } from './client'

function makeError(response?: { status: number; data: ApiErrorBody }) {
  return new AxiosError<ApiErrorBody>(
    'Request failed',
    undefined,
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
})
