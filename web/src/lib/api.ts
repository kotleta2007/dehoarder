export interface Status {
  scans: number
  tabs: number
  books: number
  jobs: number
}

export async function getStatus(): Promise<Status> {
  const response = await fetch('/api/v1/status')
  if (!response.ok) {
    throw new Error(`GET /api/v1/status failed: ${response.status}`)
  }
  return (await response.json()) as Status
}
