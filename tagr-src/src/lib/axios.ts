import axios from 'axios'

export const api = axios.create({
  baseURL: '/tags/api',
  timeout: 0,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Interceptor para manejar errores globalmente
api.interceptors.response.use(
  response => response,
  error => {
    const message = error.response?.data?.error || error.message || 'Error de conexión'
    return Promise.reject(new Error(message))
  }
)
