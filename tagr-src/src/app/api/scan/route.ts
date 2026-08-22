import { NextResponse } from 'next/server'
import { ScanMode } from '@/features/scan/domain'
import { startScanJob } from '@/features/scan/scan-job.service'
import { requireRole } from '@/lib/api/auth-guard'
import { getSearchParam } from '@/lib/api/search-params'

/**
 * Backward-compatible entry point. Scans now run as background jobs to avoid
 * proxy timeouts and the SIGSEGV crash on large libraries (issue #22); this
 * starts a job and returns its id. Poll GET /api/scan/status/[jobId] for
 * progress and the final result.
 */
export async function GET(request: Request) {
  const guard = await requireRole('tagger')
  if (!guard.authorized) return guard.response

  const { searchParams } = new URL(request.url)
  const mode = getSearchParam(searchParams, 'mode', 'string', 'full') as ScanMode

  try {
    const job = startScanJob(mode)

    return NextResponse.json({
      success: true,
      job: {
        id: job.id,
        status: job.status,
        mode: job.mode,
        startedAt: job.startedAt
      }
    })
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error starting scan'
      },
      { status: 400 }
    )
  }
}
