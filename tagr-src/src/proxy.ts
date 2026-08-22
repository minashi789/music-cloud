import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { auth } from '@/auth'

const BASE_PATH = '/tags'

function withoutBasePath(pathname: string): string {
  if (pathname === BASE_PATH || pathname === `${BASE_PATH}/`) return '/'
  if (pathname.startsWith(`${BASE_PATH}/`)) return pathname.slice(BASE_PATH.length)
  return pathname
}

function externalUrl(request: NextRequest, pathname: string): URL {
  // Используем обычный URL, а не request.nextUrl.clone(). У NextURL уже есть
  // basePath=/tags; если дополнительно записать /tags в pathname, Next.js
  // сериализует адрес как /tags/tags/....
  const url = new URL(request.url)
  url.pathname = pathname === '/' ? `${BASE_PATH}/` : `${BASE_PATH}${pathname}`
  url.search = ''
  return url
}

export async function proxy(request: NextRequest) {
  const pathname = withoutBasePath(request.nextUrl.pathname)
  const isOnLoginPage = pathname === '/login' || pathname === '/login/'
  const isAuthRoute = pathname.startsWith('/api/auth')
  const isShareRoute = pathname.startsWith('/share/')
    || pathname.startsWith('/api/share/')

  if (isAuthRoute || isShareRoute) {
    return NextResponse.next()
  }

  const session = await auth()
  const isLoggedIn = !!session

  if (isOnLoginPage && isLoggedIn) {
    return NextResponse.redirect(externalUrl(request, '/'))
  }

  if (!isOnLoginPage && !isLoggedIn) {
    return NextResponse.redirect(externalUrl(request, '/login'))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|sw\.js|manifest\.webmanifest|.*\.(?:svg|png|jpg|jpeg|gif|webp)$).*)']
}
